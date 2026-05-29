"""Local web preview for ASE trajectory files.

Run:
    python3 traj_web.py --traj demo/md.traj

The server reads ASE .traj files on demand and sends multi-frame XYZ to the
browser, where 3Dmol.js handles rendering and playback.
"""
from __future__ import annotations

import argparse
import io
import json
import mimetypes
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
WEB_ROOT = ROOT / "web"
DATA_ROOT = ROOT
SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules"}
DEFAULT_TRAJECTORY = "demo/md.traj"
TOTAL_STEPS = 20_000
TASKS: list[dict] = []
NEXT_TASK_NUM = 1


def _json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _safe_int(value: str | None, default: int, minimum: int, maximum: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


def _safe_float(value: object, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid number: {value!r}") from exc


def _format_elapsed(seconds: int) -> str:
    hours, rem = divmod(max(0, seconds), 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def _make_task_payload(task: dict) -> dict:
    task = dict(task)
    if task["state"] == "RUNNING":
        elapsed_seconds = int(time.time() - task["created_epoch"])
        current_step = min(TOTAL_STEPS - 1, elapsed_seconds * 12)
        task.update(
            {
                "elapsed": _format_elapsed(elapsed_seconds),
                "current_step": current_step,
                "progress_percent": round(current_step / TOTAL_STEPS * 100, 1),
                "message": "任务进行中",
            }
        )
    task.pop("created_epoch", None)
    return task


def _seed_tasks() -> None:
    global NEXT_TASK_NUM
    if TASKS:
        return
    TASKS.append(
        {
            "task_id": "demo-complete-001",
            "run_name": "ice_freeze_completed",
            "state": "COMPLETED",
            "queue_state": "COMPLETED",
            "elapsed": "00:43:12",
            "current_step": TOTAL_STEPS,
            "total_steps": TOTAL_STEPS,
            "progress_percent": 100,
            "message": "任务已完成",
            "created_epoch": time.time() - 3600,
            "parameters": {
                "temperature_K": 240,
                "pressure_GPa": None,
                "box_size_A": 19,
            },
            "trajectory": {
                "path": DEFAULT_TRAJECTORY,
                "frames": 182,
                "atom_count": 648,
                "composition": "O216 H432",
            },
        }
    )
    NEXT_TASK_NUM = 1


def submit_demo_task(payload: dict) -> dict:
    global NEXT_TASK_NUM

    temperature = _safe_float(payload.get("temperature_K"))
    box_size = _safe_float(payload.get("box_size_A"))
    if temperature is None:
        raise ValueError("temperature_K is required")
    if box_size is None:
        raise ValueError("box_size_A is required")
    pressure = _safe_float(payload.get("pressure_GPa"), default=None)

    task_id = f"demo-{NEXT_TASK_NUM:03d}"
    NEXT_TASK_NUM += 1
    task = {
        "task_id": task_id,
        "run_name": f"ice_freeze_{int(round(temperature))}K",
        "state": "RUNNING",
        "queue_state": "R",
        "elapsed": "00:00:00",
        "current_step": 0,
        "total_steps": TOTAL_STEPS,
        "progress_percent": 0,
        "message": "任务进行中",
        "created_epoch": time.time(),
        "parameters": {
            "temperature_K": temperature,
            "pressure_GPa": pressure,
            "box_size_A": box_size,
        },
    }
    TASKS.insert(0, task)
    return _make_task_payload(task)


def list_demo_tasks(active_task_id: str | None = None) -> dict:
    _seed_tasks()
    tasks = [_make_task_payload(task) for task in TASKS]
    active = active_task_id or (tasks[0]["task_id"] if tasks else None)
    if active and not any(task["task_id"] == active for task in tasks):
        active = tasks[0]["task_id"] if tasks else None
    return {"tasks": tasks, "active_task_id": active}


def _resolve_local_path(raw_path: str) -> Path:
    if not raw_path:
        raise ValueError("missing path")

    candidate = Path(unquote(raw_path)).expanduser()
    if not candidate.is_absolute():
        candidate = DATA_ROOT / candidate
    resolved = candidate.resolve()

    try:
        resolved.relative_to(DATA_ROOT)
    except ValueError as exc:
        raise ValueError("path must be inside the configured data root") from exc

    if not resolved.exists():
        raise ValueError(f"file not found: {resolved}")
    if resolved.suffix != ".traj":
        raise ValueError("only .traj files are supported")
    return resolved


def list_traj_files() -> list[dict]:
    files: list[dict] = []
    for path in DATA_ROOT.rglob("*.traj"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(DATA_ROOT)
        files.append({"path": str(rel), "size_bytes": path.stat().st_size})
    return sorted(files, key=lambda item: item["path"])


def load_traj_as_xyz(path: Path, stride: int, max_frames: int) -> dict:
    try:
        from ase.io import read, write
    except ImportError as exc:
        raise RuntimeError("ASE is not installed. Run `python3 -m pip install -r requirements.txt`.") from exc

    frames = read(str(path), index=f"::{stride}")
    if not isinstance(frames, list):
        frames = [frames]
    truncated = len(frames) > max_frames
    frames = frames[:max_frames]
    if not frames:
        raise ValueError("trajectory has no frames")

    buffer = io.StringIO()
    write(buffer, frames, format="xyz")
    atom_count = len(frames[0])
    symbols = {}
    for symbol in frames[0].get_chemical_symbols():
        symbols[symbol] = symbols.get(symbol, 0) + 1

    return {
        "path": str(path.relative_to(DATA_ROOT)),
        "stride": stride,
        "frames": len(frames),
        "atom_count": atom_count,
        "symbols": symbols,
        "truncated": truncated,
        "xyz": buffer.getvalue(),
    }


class TrajPreviewHandler(BaseHTTPRequestHandler):
    server_version = "vibematsci-traj-web/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self._send_static(WEB_ROOT / "index.html")
            elif parsed.path == "/api/tasks":
                params = parse_qs(parsed.query)
                active_task_id = params.get("active_task_id", [None])[0]
                self._send_json(list_demo_tasks(active_task_id))
            elif parsed.path == "/api/files":
                self._send_json({"files": list_traj_files()})
            elif parsed.path == "/api/trajectory":
                self._send_trajectory(parsed.query)
            else:
                requested = (WEB_ROOT / parsed.path.lstrip("/")).resolve()
                try:
                    requested.relative_to(WEB_ROOT)
                except ValueError:
                    self._send_error(HTTPStatus.NOT_FOUND, "not found")
                    return
                self._send_static(requested)
        except Exception as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if parsed.path != "/api/tasks":
                self._send_error(HTTPStatus.NOT_FOUND, "not found")
                return
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            payload = json.loads(body)
            task = submit_demo_task(payload)
            self._send_json({"task": task, "tasks": list_demo_tasks(task["task_id"])["tasks"]})
        except Exception as exc:
            self._send_error(HTTPStatus.BAD_REQUEST, str(exc))

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")

    def _send_static(self, path: Path) -> None:
        if not path.exists() or not path.is_file():
            self._send_error(HTTPStatus.NOT_FOUND, "not found")
            return
        data = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_error(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def _send_trajectory(self, query: str) -> None:
        params = parse_qs(query)
        path = _resolve_local_path(params.get("path", [""])[0])
        stride = _safe_int(params.get("stride", [None])[0], default=1, minimum=1, maximum=1000)
        max_frames = _safe_int(params.get("max_frames", [None])[0], default=250, minimum=1, maximum=2000)
        self._send_json(load_traj_as_xyz(path, stride=stride, max_frames=max_frames))


def main() -> None:
    global DATA_ROOT

    parser = argparse.ArgumentParser(description="Preview ASE .traj files in a browser.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--data-root", default=None, help="Directory to search for .traj files.")
    parser.add_argument("--traj", default="demo/md.traj", help="Default trajectory path relative to vibematsci.")
    args = parser.parse_args()

    traj_arg = Path(args.traj).expanduser()
    if args.data_root is not None:
        DATA_ROOT = Path(args.data_root).expanduser().resolve()
    elif traj_arg.is_absolute():
        DATA_ROOT = traj_arg.parent.resolve()
        args.traj = traj_arg.name

    default_path = _resolve_local_path(args.traj)
    print(f"Data root: {DATA_ROOT}")
    print(f"Default trajectory: {default_path.relative_to(DATA_ROOT)}")
    server = ThreadingHTTPServer((args.host, args.port), TrajPreviewHandler)
    print(f"Open http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
