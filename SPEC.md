# vibematsci Minimal Demo

## Value Proposition

vibematsci is a minimal conversational demo for molecular-dynamics jobs. A user can ask the assistant to submit a chemistry simulation with a few parameters, then check the task status and preview the completed trajectory in a shared frontend view.

This demo is intentionally fake-data only. It must run locally without SSH, Slurm, remote upload, real job submission, or supercomputer access.

**Core actions**:

1. Submit a demo simulation task.
2. View a demo task, including running progress or completed trajectory preview.

## Why LLM?

**Conversational win**: The user can describe a simulation request in natural language, for example "提交一个 240 K, 0.1 GPa, 19 A 盒子的模拟任务", instead of manually editing shell commands or Slurm scripts.

**LLM adds**: The assistant extracts and normalizes parameters, fills demo defaults, explains missing values, and summarizes task status in plain language.

**What LLM lacks**: The assistant needs app data for task state and trajectory preview. In the demo, those are mock data plus the bundled `demo/md.traj`.

## UX Flows

Submit task:

1. User provides temperature, pressure, and system size.
2. Assistant calls the mock submit action.
3. The shared view shows the created task id, normalized parameters, and initial mock state.

View task:

1. User asks to view the latest task or a task id.
2. The shared view shows queue state, elapsed time, current MD step, total MD steps, and progress.
3. If the task is queued or running, the view and assistant show `任务进行中`.
4. If the task is complete, the view shows the 3D trajectory preview using `demo/md.traj`.

## Tools And Views

### View Tool: `manage_demo_tasks`

Use one shared view for the whole demo. This keeps the implementation small and gives both the human and assistant the same task state.

**Input**:

```json
{
  "active_task_id": "demo-001"
}
```

`active_task_id` is optional. If omitted, the view shows the latest mock task.

**Output**:

```json
{
  "tasks": [
    {
      "task_id": "demo-001",
      "run_name": "ice_freeze_240K",
      "state": "RUNNING",
      "queue_state": "R",
      "elapsed": "00:17:42",
      "current_step": 8400,
      "total_steps": 20000,
      "progress_percent": 42,
      "message": "任务进行中",
      "parameters": {
        "temperature_K": 240,
        "pressure_GPa": 0.1,
        "box_size_A": 19
      }
    }
  ],
  "active_task_id": "demo-001"
}
```

**UI**:

- Compact parameter form: temperature, pressure, box size.
- Submit button that creates a mock task.
- Task status panel showing id, state, queue state, elapsed time, current step, total steps, and progress.
- Running/queued state text: `任务进行中`.
- Completed state preview panel rendering the bundled trajectory.

**State**:

- Demo task data lives in the Skybridge server process memory so the LLM and human share the same task list through the view output.
- Browser state is only for local UI focus, such as the selected task or selected trajectory frame.
- Persistence is not required for the MVP.
- The view includes one pre-seeded completed task so the 3D preview is immediately demonstrable.

### Tool: `submit_demo_task`

Creates a fake task. No real SSH or Slurm operation is allowed.
After this tool returns, the assistant or view should refresh/open `manage_demo_tasks` with the returned `task_id` as `active_task_id`.

**Input**:

```json
{
  "temperature_K": 240,
  "pressure_GPa": 0.1,
  "box_size_A": 19
}
```

**Output**:

```json
{
  "task_id": "demo-001",
  "run_name": "ice_freeze_240K",
  "state": "RUNNING",
  "queue_state": "R",
  "elapsed": "00:00:00",
  "current_step": 0,
  "total_steps": 20000,
  "progress_percent": 0,
  "message": "任务进行中",
  "parameters": {
    "temperature_K": 240,
    "pressure_GPa": 0.1,
    "box_size_A": 19
  }
}
```

**Defaults**:

- `temperature_K`: required
- `pressure_GPa`: optional, default `null`
- `box_size_A`: required
- `total_steps`: fixed demo value `20000`
- `trajectory_path`: fixed demo value `demo/md.traj` for completed tasks

## Minimal Demo Behavior

The MVP only needs three visible states:

1. Empty state: no submitted task, but a completed sample task may be available for preview.
2. Running task: newly submitted task shows `任务进行中`, queue/progress fields, and no trajectory preview.
3. Completed sample task: shows status complete and renders `demo/md.traj` in the 3D viewer.

The demo does not need:

- Real SSH.
- Real Slurm commands.
- Remote file upload/download.
- Authentication.
- Database persistence.
- Full job history management.
- Real-time polling.
- Failure recovery.

## Trajectory Preview

Use the existing local `.traj` preview path:

- Backend/Python reads `demo/md.traj` with ASE.
- The server converts selected frames to multi-frame XYZ.
- The frontend renders the XYZ frames with 3Dmol.js.
- The UI should include basic frame playback or a frame slider.

The browser must not parse ASE `.traj` directly.

## Acceptance Criteria

- The app runs locally as a minimal demo.
- A user can submit a mock task with temperature, pressure, and box size.
- The created task displays a fake task id and normalized parameters.
- A running task displays `任务进行中`.
- A running task displays queue state, elapsed time, current step, total steps, and progress percent.
- A completed sample task displays the bundled `demo/md.traj` in the frontend 3D preview.
- The demo works without SSH, Slurm, or remote filesystem access.
