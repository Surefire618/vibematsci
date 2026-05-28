"""vibematsci — MCP server for water-freezing MD with MACE-MPA-0 on Slurm clusters.

Exposes tools to prepare, submit, monitor, and visualize ASE-driven MD jobs
that run on a remote supercomputer reachable via SSH.

Cluster connection details (host, work root, micromamba binary, env name) are
read from environment variables (see .env.example). Copy `.env.example` to
`.env` and edit before first use.

Run locally:  python mcp_server.py
Register:     claude mcp add vibematsci -- python /abs/path/mcp_server.py
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

HERE = Path(__file__).resolve().parent

# Load .env if present (no error if missing)
try:
    from dotenv import load_dotenv
    load_dotenv(HERE / ".env")
except ImportError:
    pass

# -- configuration ------------------------------------------------------------
# MODE = "demo" (default): all tools return a bundled trajectory without
#        touching any cluster. Lets anyone try the workflow with no setup.
# MODE = "live": tools go to the cluster over SSH.
MODE        = os.environ.get("VIBEMATSCI_MODE", "demo").lower()
REMOTE_HOST = os.environ.get("VIBEMATSCI_HOST", "cluster")
REMOTE_ROOT = os.environ.get("VIBEMATSCI_WORK_ROOT", "~/vibematsci_runs")
MACE_ENV    = os.environ.get("VIBEMATSCI_MACE_ENV", "mace")
MICROMAMBA  = os.environ.get("VIBEMATSCI_MICROMAMBA", "micromamba")

SCRIPTS_DIR   = HERE / "scripts"
BUILD_SCRIPT  = SCRIPTS_DIR / "build_structure.py"
MD_SCRIPT     = SCRIPTS_DIR / "run_md.py"
SUBMIT_SCRIPT = SCRIPTS_DIR / "submit.sh"

DEMO_DIR     = HERE / "demo"
DEMO_JOB_ID  = "DEMO-001"

mcp = FastMCP("vibematsci")


# -- helpers ------------------------------------------------------------------
def _ssh(cmd: str, timeout: int = 60) -> dict:
    r = subprocess.run(
        ["ssh", REMOTE_HOST, cmd],
        capture_output=True, text=True, timeout=timeout,
    )
    return {"returncode": r.returncode,
            "stdout": r.stdout,
            "stderr": r.stderr}


def _scp_push(local: Path, remote: str) -> dict:
    r = subprocess.run(
        ["scp", "-q", str(local), f"{REMOTE_HOST}:{remote}"],
        capture_output=True, text=True, timeout=180,
    )
    return {"returncode": r.returncode,
            "stdout": r.stdout,
            "stderr": r.stderr}


def _remote_workdir(run_name: str) -> str:
    if "/" in run_name or run_name in (".", "..", ""):
        raise ValueError(f"invalid run_name: {run_name!r}")
    return f"{REMOTE_ROOT}/{run_name}"


def _demo_n_frames() -> int:
    """Count frames in the bundled demo trajectory."""
    try:
        from ase.io import iread
        return sum(1 for _ in iread(str(DEMO_DIR / "md.traj")))
    except Exception:
        return -1


def _demo_config() -> dict:
    p = DEMO_DIR / "config.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}


# -- MCP tools ----------------------------------------------------------------
@mcp.tool()
def check_access() -> dict:
    """Check SSH access to the cluster and verify the MACE python env is usable.

    Returns: SSH status, remote hostname, GPU-related Slurm partitions,
    versions of mace/ase/torch in the remote env, and whether MPA-0 weights
    are already cached on the cluster. In demo mode, reports the bundled
    trajectory.
    """
    if MODE == "demo":
        n_frames = len(list(DEMO_DIR.glob("md.traj"))) and _demo_n_frames()
        return {
            "mode": "demo",
            "demo_dir": str(DEMO_DIR),
            "trajectory_frames": n_frames,
            "note": "Set VIBEMATSCI_MODE=live to drive a real cluster.",
        }
    out: dict = {"mode": "live", "host": REMOTE_HOST, "work_root": REMOTE_ROOT}
    r = _ssh("hostname")
    out["ssh_ok"] = r["returncode"] == 0
    out["remote_hostname"] = r["stdout"].strip()
    if not out["ssh_ok"]:
        out["error"] = r["stderr"].strip()
        return out

    r = _ssh("sinfo -h -o '%P %a %D %T' | grep -iE 'gpu|interactive' | head -20")
    out["partitions"] = r["stdout"].strip()

    probe = (
        f"bash -lc '{MICROMAMBA} run -n {MACE_ENV} python -c "
        f'"import mace, ase, torch; '
        f'print(mace.__version__, ase.__version__, torch.__version__)"\' 2>&1 | tail -1'
    )
    r = _ssh(probe, timeout=120)
    out["mace_env_versions"] = r["stdout"].strip()

    r = _ssh("ls ~/.cache/mace/macempa0mediummodel 2>/dev/null && echo present || echo missing")
    out["mpa0_weights_cached"] = "present" in r["stdout"]
    return out


@mcp.tool()
def prepare_simulation(
    run_name: str,
    temperature_K: float = 240.0,
    box_size_A: float = 19.0,
    pressure_GPa: Optional[float] = None,
    n_fixed_layers: int = 0,
    n_steps: int = 20_000,
    timestep_fs: float = 0.5,
    log_every: int = 50,
    traj_every: int = 100,
) -> dict:
    """Create a parameterized simulation directory on the cluster.

    Pushes build_structure.py, run_md.py, submit.sh, and a config.json
    carrying all simulation parameters.

    Args:
        run_name: leaf directory under the remote work root.
        temperature_K: NVT/NPT target temperature in K.
        box_size_A: requested cubic edge length; rounded to nearest multiple
            of the cubic-ice-Ic lattice constant 6.358 Å.
        pressure_GPa: if set, NPT (Berendsen); if None, NVT (Langevin).
        n_fixed_layers: bottom ice unit cells held rigid via FixAtoms
            (1 layer = 6.358 Å = 2 H₂O bilayers). 0 = no fixing.
        n_steps: total MD steps.
        timestep_fs: timestep in fs.
        log_every: log every N steps.
        traj_every: trajectory frame every N steps.
    """
    if MODE == "demo":
        return {
            "mode": "demo",
            "run_name": run_name,
            "config": {
                "temperature_K": float(temperature_K),
                "box_size_A": float(box_size_A),
                "pressure_GPa": (None if pressure_GPa is None else float(pressure_GPa)),
                "n_fixed_layers": int(n_fixed_layers),
                "n_steps": int(n_steps),
                "timestep_fs": float(timestep_fs),
            },
            "demo_config_actually_used": _demo_config(),
            "note": (
                "Demo mode: parameters are recorded but the bundled trajectory "
                f"(see {DEMO_DIR}) is what every tool returns."
            ),
            "next": f"call submit_job(run_name='{run_name}')",
        }

    for p in (BUILD_SCRIPT, MD_SCRIPT, SUBMIT_SCRIPT):
        if not p.exists():
            return {"error": f"local template missing: {p.relative_to(HERE)}"}

    work_dir = _remote_workdir(run_name)
    r = _ssh(f"mkdir -p {shlex.quote(work_dir)}")
    if r["returncode"] != 0:
        return {"error": f"mkdir failed: {r['stderr']}"}

    for p in (BUILD_SCRIPT, MD_SCRIPT, SUBMIT_SCRIPT):
        r = _scp_push(p, f"{work_dir}/{p.name}")
        if r["returncode"] != 0:
            return {"error": f"scp {p.name}: {r['stderr']}"}

    config = {
        "temperature_K": float(temperature_K),
        "box_size_A": float(box_size_A),
        "pressure_GPa": (None if pressure_GPa is None else float(pressure_GPa)),
        "n_fixed_layers": int(n_fixed_layers),
        "n_steps": int(n_steps),
        "timestep_fs": float(timestep_fs),
        "log_every": int(log_every),
        "traj_every": int(traj_every),
    }
    local_cfg = HERE / f".{run_name}.config.json"
    local_cfg.write_text(json.dumps(config, indent=2))
    r = _scp_push(local_cfg, f"{work_dir}/config.json")
    local_cfg.unlink(missing_ok=True)
    if r["returncode"] != 0:
        return {"error": f"scp config.json: {r['stderr']}"}

    return {
        "work_dir": work_dir,
        "config": config,
        "files_pushed": ["build_structure.py", "run_md.py", "submit.sh", "config.json"],
        "next": f"call submit_job(run_name='{run_name}')",
    }


@mcp.tool()
def submit_job(run_name: str) -> dict:
    """Submit submit.sh in the run directory via sbatch."""
    if MODE == "demo":
        return {
            "mode": "demo",
            "job_id": DEMO_JOB_ID,
            "run_name": run_name,
            "note": "Demo mode: no real Slurm submission. Job 'completes' immediately.",
        }
    work_dir = _remote_workdir(run_name)
    r = _ssh(f"cd {shlex.quote(work_dir)} && sbatch submit.sh")
    line = r["stdout"].strip()
    job_id = None
    for tok in line.split():
        if tok.isdigit():
            job_id = int(tok)
            break
    return {
        "job_id": job_id,
        "sbatch_output": line,
        "stderr": r["stderr"].strip(),
        "work_dir": work_dir,
    }


@mcp.tool()
def monitor_job(job_id) -> dict:
    """Return current state of a Slurm job. Falls back to sacct for finished jobs."""
    if MODE == "demo":
        return {
            "mode": "demo", "job_id": str(job_id), "running": False,
            "state": "COMPLETED", "elapsed": "00:35:00", "exit_code": "0:0",
        }
    r = _ssh(f"squeue -j {job_id} -h -o '%T|%M|%L|%R'")
    if r["stdout"].strip():
        parts = r["stdout"].strip().split("|") + ["", "", "", ""]
        return {
            "job_id": job_id, "running": True,
            "state": parts[0], "elapsed": parts[1],
            "remaining": parts[2], "reason_or_node": parts[3],
        }
    r = _ssh(f"sacct -j {job_id} -n -P -o State,Elapsed,ExitCode | head -1")
    line = r["stdout"].strip()
    if not line:
        return {"job_id": job_id, "running": False, "state": "UNKNOWN"}
    s, e, ec = (line.split("|") + ["", "", ""])[:3]
    return {"job_id": job_id, "running": False,
            "state": s, "elapsed": e, "exit_code": ec}


@mcp.tool()
def list_jobs() -> dict:
    """List your Slurm jobs (`squeue -u $USER`)."""
    if MODE == "demo":
        return {"mode": "demo",
                "jobs": f"{DEMO_JOB_ID}  gpu  demo  COMPLETED  00:35:00  0:00  (demo)"}
    r = _ssh("squeue -u $USER -o '%i %P %j %T %M %L %R'")
    return {"jobs": r["stdout"]}


@mcp.tool()
def cancel_job(job_id) -> dict:
    """Cancel a Slurm job (`scancel`)."""
    if MODE == "demo":
        return {"mode": "demo", "ok": True,
                "note": "Demo mode: nothing to cancel."}
    r = _ssh(f"scancel {job_id}")
    return {"ok": r["returncode"] == 0, "stderr": r["stderr"].strip()}


@mcp.tool()
def tail_log(run_name: str, lines: int = 30) -> dict:
    """Tail md.log and the most recent .out/.err file in the run directory."""
    if MODE == "demo":
        log = DEMO_DIR / "md.log"
        if not log.exists():
            return {"mode": "demo", "error": "demo md.log missing"}
        text = log.read_text().splitlines()
        return {
            "mode": "demo",
            "run_name": run_name,
            "output": "\n".join(text[-lines:]),
        }
    work_dir = _remote_workdir(run_name)
    r = _ssh(
        f"cd {shlex.quote(work_dir)} && "
        f"(echo '=== md.log ==='; tail -n {lines} md.log 2>/dev/null; "
        f" echo '=== latest .out ==='; ls -1t *.out 2>/dev/null | head -1 | xargs -r tail -n {lines}; "
        f" echo '=== latest .err ==='; ls -1t *.err 2>/dev/null | head -1 | xargs -r tail -n {lines})"
    )
    return {"work_dir": work_dir, "output": r["stdout"]}


@mcp.tool()
def pull_results(run_name: str, local_dir: str) -> dict:
    """Download trajectory + logs + structure files from the run directory.

    Pulls: md.traj, md.log, initial.xyz, initial.traj, config.json,
    n_fixed_atoms.txt, *.out, *.err via rsync.
    """
    if MODE == "demo":
        local = Path(local_dir).expanduser().resolve()
        local.mkdir(parents=True, exist_ok=True)
        copied = []
        for src in DEMO_DIR.iterdir():
            dst = local / src.name
            shutil.copy2(src, dst)
            copied.append(src.name)
        return {
            "mode": "demo",
            "local_dir": str(local),
            "files": sorted(copied),
            "next": f"call view_trajectory(path='{local}/md.traj')",
        }
    if shutil.which("rsync") is None:
        return {"error": "rsync not installed on local machine"}
    work_dir = _remote_workdir(run_name)
    local = Path(local_dir).expanduser().resolve()
    local.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        ["rsync", "-az",
         "--include=md.traj", "--include=md.log",
         "--include=initial.xyz", "--include=initial.traj",
         "--include=config.json", "--include=n_fixed_atoms.txt",
         "--include=*.out", "--include=*.err",
         "--exclude=*",
         f"{REMOTE_HOST}:{work_dir}/", f"{local}/"],
        capture_output=True, text=True, timeout=600,
    )
    files = sorted(p.name for p in local.iterdir())
    return {
        "local_dir": str(local),
        "files": files,
        "rsync_returncode": r.returncode,
        "stderr": r.stderr.strip(),
    }


@mcp.tool()
def get_demo_trajectory() -> dict:
    """Return the path and metadata of the bundled demo trajectory.

    The demo is a ~9 ps NVT freezing simulation of a 19.07 Å cubic water box
    at 50 K with 2 fixed bottom ice layers (216 H₂O, 648 atoms, MACE-MPA-0).
    """
    traj = DEMO_DIR / "md.traj"
    if not traj.exists():
        return {"error": "demo trajectory missing from repo"}
    return {
        "trajectory_path": str(traj),
        "log_path": str(DEMO_DIR / "md.log"),
        "initial_xyz_path": str(DEMO_DIR / "initial.xyz"),
        "config": _demo_config(),
        "n_frames": _demo_n_frames(),
        "view_command": f"ase gui {traj}",
    }


@mcp.tool()
def view_trajectory(path: str = "") -> dict:
    """Open a local trajectory / structure with `ase gui` (background process).

    If `path` is omitted (or empty), opens the bundled demo trajectory.
    """
    if not path:
        path = str(DEMO_DIR / "md.traj")
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return {"error": f"file not found: {p}"}
    if shutil.which("ase") is None:
        return {
            "error": "`ase` CLI not installed locally",
            "fallback_command": f"ase gui {p}",
        }
    proc = subprocess.Popen(
        ["ase", "gui", str(p)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"pid": proc.pid, "path": str(p)}


if __name__ == "__main__":
    mcp.run()
