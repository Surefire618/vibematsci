# vibematsci

An [MCP](https://modelcontextprotocol.io) server that drives MACE-MPA-0
water-freezing molecular-dynamics simulations on a remote Slurm cluster.

The server lets an LLM agent (e.g. Claude Code) prepare, submit, monitor, and
visualize jobs end-to-end via a small set of tools — temperature, box size,
pressure, and the number of fixed bottom ice layers are all exposed as
parameters.

## Modes

- **demo** (default): every tool returns the bundled trajectory under `demo/`
  — a ~9 ps NVT freezing simulation of a 19.07 Å cubic water box at 50 K
  with 2 fixed bottom ice layers (216 H₂O, 648 atoms, MACE-MPA-0). No
  cluster, no setup required. Anyone cloning this repo can walk through
  prepare → submit → monitor → pull → view and get a real trajectory back.
- **live**: tools go to a Slurm cluster over SSH and run the real simulation.
  Set `VIBEMATSCI_MODE=live` plus the cluster connection variables (see
  `.env.example`).

## Layout

```
vibematsci/
├── mcp_server.py          # FastMCP server, all tools live here
├── scripts/               # Pushed to the cluster by prepare_simulation (live mode)
│   ├── build_structure.py # Builds cubic box: partial ice + liquid water
│   ├── run_md.py          # ASE NVT/NPT MD with MACE-MPA-0
│   └── submit.sh          # Slurm wrapper (1 A100, 2 h)
├── demo/                  # Bundled demo trajectory (used in demo mode)
│   ├── md.traj            # 182 frames, 648 atoms, 19.07 Å cube
│   ├── md.log
│   ├── initial.xyz
│   ├── config.json
│   └── n_fixed_atoms.txt
├── .env.example           # Cluster connection settings template
├── requirements.txt
└── README.md
```

## Setup

```bash
git clone <repo-url>
cd vibematsci
pip install -r requirements.txt
cp .env.example .env       # then edit
```

## Skybridge GPT app demo

This repo also includes a minimal Skybridge app described by `SPEC.md`. It is a
fake-data-only demo: submitting a task creates an in-memory mock job, viewing a
running job shows `任务进行中`, and the completed sample task previews the
bundled `demo/md.traj` trajectory in a 3Dmol.js viewer.

```bash
npm install
npm test
npm run build
npm run dev
```

The Skybridge dev server prints local DevTools and MCP URLs. Use the
`manage_demo_tasks` view tool to open the shared task workspace and
`submit_demo_task` to create a mock running simulation.

On the **cluster**, you need:

- A Slurm-managed GPU partition (the bundled `submit.sh` requests one A100).
- A micromamba (or conda) env with `mace-torch`, `ase`, and `torch + CUDA`.
  By default the server looks for an env named `mace`.
- MACE-MPA-0 weights cached at `~/.cache/mace/macempa0mediummodel`
  (the first call to `mace_mp(model="medium-mpa-0")` downloads them).

On your **local machine**:

- Passwordless `ssh $VIBEMATSCI_HOST` (typically via `~/.ssh/config`).
- `rsync` for `pull_results`, `ase` for `view_trajectory`.

## Register with Claude Code

```bash
claude mcp add vibematsci -- python /abs/path/to/vibematsci/mcp_server.py
```

Or add to `~/.claude/.mcp.json`:

```json
{
  "mcpServers": {
    "vibematsci": {
      "command": "python",
      "args": ["/abs/path/to/vibematsci/mcp_server.py"]
    }
  }
}
```

## Tools

| Tool | Purpose |
| --- | --- |
| `check_access` | SSH probe + GPU partitions + remote env versions + MPA-0 cache check |
| `prepare_simulation` | Push scripts + `config.json` to a fresh run dir on the cluster |
| `submit_job` | `sbatch submit.sh`, returns the Slurm job id |
| `monitor_job` | `squeue` / `sacct` state, elapsed, remaining |
| `list_jobs` | Your full `squeue` |
| `cancel_job` | `scancel` |
| `tail_log` | Tail `md.log` and the latest `.out`/`.err` |
| `pull_results` | `rsync` trajectory + logs back locally |
| `view_trajectory` | Open a local `.traj`/`.xyz` with `ase gui` (defaults to the bundled demo) |
| `get_demo_trajectory` | Return path + metadata of the bundled demo trajectory |

## Simulation parameters

Passed to `prepare_simulation`:

| Param | Default | Notes |
| --- | --- | --- |
| `run_name` | — | leaf dir under `$VIBEMATSCI_WORK_ROOT` |
| `temperature_K` | `240.0` | NVT/NPT target |
| `box_size_A` | `19.0` | cubic edge; snapped to nearest multiple of 6.358 Å (cubic-ice-Ic) |
| `pressure_GPa` | `None` | `None` ⇒ NVT (Langevin); set ⇒ NPT (Berendsen) |
| `n_fixed_layers` | `0` | bottom ice unit cells held rigid; 1 layer = 6.358 Å ≈ 2 H₂O bilayers |
| `n_steps` | `20000` | total MD steps |
| `timestep_fs` | `0.5` | timestep in fs |
| `log_every` | `50` | log every N steps |
| `traj_every` | `100` | trajectory frame every N steps |

## Example: a single demo run via the agent

```
prepare_simulation(run_name="ice_freeze_50K",
                   temperature_K=50,
                   box_size_A=19,
                   n_fixed_layers=2,
                   n_steps=20000)
submit_job(run_name="ice_freeze_50K")
monitor_job(job_id=...)
tail_log(run_name="ice_freeze_50K", lines=20)
pull_results(run_name="ice_freeze_50K", local_dir="~/runs/ice_freeze_50K")
view_trajectory(path="~/runs/ice_freeze_50K/md.traj")
```

## Web trajectory preview

You can preview an ASE `.traj` file in a browser without opening `ase gui`:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python traj_web.py --traj demo/md.traj
```

Then open <http://127.0.0.1:8765/>. The local server reads `.traj` files
with ASE, converts selected frames to multi-frame XYZ, and renders them in the
browser with 3Dmol.js. Use `stride` and `frames` in the UI to reduce payload
size for long MD runs.

To preview a downloaded run outside this repository:

```bash
.venv/bin/python traj_web.py --data-root ~/runs/ice_freeze_50K --traj md.traj
```

## License

No license file is included. All rights reserved; reuse with permission only.
