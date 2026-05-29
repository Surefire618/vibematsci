export type DemoTaskState = "RUNNING" | "COMPLETED";

export type DemoParameters = {
  temperature_K: number;
  pressure_GPa: number | null;
  box_size_A: number;
};

export type DemoTask = {
  task_id: string;
  run_name: string;
  state: DemoTaskState;
  queue_state: string;
  elapsed: string;
  current_step: number;
  total_steps: number;
  progress_percent: number;
  message: string;
  parameters: DemoParameters;
  trajectory?: {
    path: string;
    frames: number;
    atom_count: number;
    composition: string;
  };
};

export const TOTAL_STEPS = 20_000;
export const TRAJECTORY_PATH = "demo/md.traj";

export function createCompletedSampleTask(): DemoTask {
  return {
    task_id: "demo-complete-001",
    run_name: "ice_freeze_completed",
    state: "COMPLETED",
    queue_state: "COMPLETED",
    elapsed: "00:43:12",
    current_step: TOTAL_STEPS,
    total_steps: TOTAL_STEPS,
    progress_percent: 100,
    message: "任务已完成",
    parameters: {
      temperature_K: 240,
      pressure_GPa: null,
      box_size_A: 19,
    },
    trajectory: {
      path: TRAJECTORY_PATH,
      frames: 182,
      atom_count: 648,
      composition: "O216 H432",
    },
  };
}

export function createRunningTask(input: {
  index: number;
  temperature_K: number;
  pressure_GPa?: number | null;
  box_size_A: number;
}): DemoTask {
  const temperature = Number(input.temperature_K);
  const pressure = input.pressure_GPa ?? null;
  const boxSize = Number(input.box_size_A);

  if (!Number.isFinite(temperature)) {
    throw new Error("temperature_K is required");
  }
  if (!Number.isFinite(boxSize)) {
    throw new Error("box_size_A is required");
  }
  if (pressure !== null && !Number.isFinite(Number(pressure))) {
    throw new Error("pressure_GPa must be a number or null");
  }

  return {
    task_id: `demo-${String(input.index).padStart(3, "0")}`,
    run_name: `ice_freeze_${Math.round(temperature)}K`,
    state: "RUNNING",
    queue_state: "R",
    elapsed: "00:00:00",
    current_step: 0,
    total_steps: TOTAL_STEPS,
    progress_percent: 0,
    message: "任务进行中",
    parameters: {
      temperature_K: temperature,
      pressure_GPa: pressure === null ? null : Number(pressure),
      box_size_A: boxSize,
    },
  };
}

export function createInitialTasks(): DemoTask[] {
  return [createCompletedSampleTask()];
}
