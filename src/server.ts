import { McpServer } from "skybridge/server";
import { z } from "zod";
import {
  createInitialTasks,
  createRunningTask,
  type DemoTask,
} from "./lib/demo-data.js";
import { bundledTrajectoryPreview } from "./lib/trajectory-preview.js";

let nextTaskIndex = 1;
let tasks: DemoTask[] = createInitialTasks();

type TrajectoryPreview = {
  path: string;
  frames: number;
  atom_count: number;
  composition: string;
  xyz: string;
};

function readTrajectoryPreview(): TrajectoryPreview {
  return bundledTrajectoryPreview satisfies TrajectoryPreview;
}

function manageDemoTasksOutput(activeTaskId?: string) {
  const active = activeTaskId && tasks.some((task) => task.task_id === activeTaskId)
    ? activeTaskId
    : tasks[0]?.task_id;

  return {
    structuredContent: {
      tasks,
      active_task_id: active,
    },
    content: [
      {
        type: "text" as const,
        text: "vibematsci demo task workspace is ready.",
      },
    ],
    _meta: {
      trajectoryPreview: readTrajectoryPreview(),
    },
    isError: false,
  };
}

const server = new McpServer(
  {
    name: "vibematsci-demo",
    version: "0.0.1",
  },
  { capabilities: {} },
)
  .registerTool(
    {
      name: "manage_demo_tasks",
      description: "Open the vibematsci demo task workspace.",
      inputSchema: {
        active_task_id: z.string().optional(),
      },
      annotations: {
        title: "View vibematsci demo tasks",
        readOnlyHint: true,
        destructiveHint: false,
        openWorldHint: false,
      },
      _meta: {
        "openai/toolInvocation/invoking": "Opening vibematsci demo tasks...",
        "openai/toolInvocation/invoked": "vibematsci demo tasks ready.",
      },
      view: {
        component: "manage-demo-tasks",
        domain: "https://skybridge.tech",
        description: "Submit and view demo molecular-dynamics tasks",
        csp: {
          resourceDomains: ["https://3Dmol.org", "https://3dmol.org"],
        },
      },
    },
    async ({ active_task_id }) => manageDemoTasksOutput(active_task_id),
  )
  .registerTool(
    {
      name: "submit_demo_task",
      description: "Create a fake vibematsci simulation task with mock progress.",
      inputSchema: {
        temperature_K: z.number().describe("Simulation temperature in Kelvin."),
        pressure_GPa: z.number().nullable().optional().describe("Optional pressure in GPa."),
        box_size_A: z.number().describe("Cubic system size in Angstrom."),
      },
      annotations: {
        title: "Submit demo simulation task",
        readOnlyHint: false,
        destructiveHint: false,
        openWorldHint: false,
      },
      _meta: {
        "openai/toolInvocation/invoking": "Submitting demo simulation task...",
        "openai/toolInvocation/invoked": "Demo simulation task submitted.",
      },
    },
    async ({ temperature_K, pressure_GPa, box_size_A }) => {
      const task = createRunningTask({
        index: nextTaskIndex,
        temperature_K,
        pressure_GPa,
        box_size_A,
      });
      nextTaskIndex += 1;
      tasks = [task, ...tasks];

      return {
        structuredContent: { task },
        content: [
          {
            type: "text" as const,
            text: `Demo task ${task.task_id} submitted. ${task.message}`,
          },
        ],
        isError: false,
      };
    },
  );

if (process.env.NODE_ENV === "production") {
  const { default: manifest } = await import("./vite-manifest.js");
  server.setViteManifest(manifest);
}

export default await server.run();

export type AppType = typeof server;
