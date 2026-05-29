import assert from "node:assert/strict";
import test from "node:test";
import {
  createCompletedSampleTask,
  createInitialTasks,
  createRunningTask,
  TOTAL_STEPS,
  TRAJECTORY_PATH,
} from "./demo-data.js";
import { bundledTrajectoryPreview } from "./trajectory-preview.js";

test("createRunningTask normalizes submitted parameters", () => {
  const task = createRunningTask({
    index: 7,
    temperature_K: 240,
    pressure_GPa: 0.1,
    box_size_A: 19,
  });

  assert.equal(task.task_id, "demo-007");
  assert.equal(task.state, "RUNNING");
  assert.equal(task.message, "任务进行中");
  assert.equal(task.total_steps, TOTAL_STEPS);
  assert.deepEqual(task.parameters, {
    temperature_K: 240,
    pressure_GPa: 0.1,
    box_size_A: 19,
  });
});

test("completed sample task points at bundled trajectory", () => {
  const task = createCompletedSampleTask();

  assert.equal(task.state, "COMPLETED");
  assert.equal(task.current_step, TOTAL_STEPS);
  assert.equal(task.trajectory?.path, TRAJECTORY_PATH);
  assert.equal(task.trajectory?.atom_count, 648);
});

test("initial tasks include previewable completed sample", () => {
  const tasks = createInitialTasks();

  assert.equal(tasks.length, 1);
  assert.equal(tasks[0]?.task_id, "demo-complete-001");
  assert.equal(tasks[0]?.trajectory?.composition, "O216 H432");
});

test("bundled trajectory preview is multi-frame production data", () => {
  assert.equal(bundledTrajectoryPreview.path, TRAJECTORY_PATH);
  assert.equal(bundledTrajectoryPreview.frames, 12);
  assert.equal(bundledTrajectoryPreview.atom_count, 648);
  assert.equal(bundledTrajectoryPreview.composition, "O216 H432");
});
