import "@/index.css";
import { useEffect, useMemo, useRef, useState } from "react";
import { useCallTool, useToolInfo } from "../helpers.js";
import type { DemoTask } from "../lib/demo-data.js";

type MoleculeViewer = {
  clear: () => void;
  addModelsAsFrames: (data: string, format: string) => void;
  setBackgroundColor: (color: string) => void;
  setStyle: (selector: object, style: object) => void;
  addStyle: (selector: object, style: object) => void;
  setFrame: (frame: number) => void;
  zoomTo: () => void;
  render: () => void;
  resize: () => void;
};

declare global {
  interface Window {
    $3Dmol?: {
      createViewer: (element: HTMLElement) => MoleculeViewer;
    };
  }
}

type ToolOutput = {
  tasks: DemoTask[];
  active_task_id?: string;
};

type TrajectoryPreview = {
  path: string;
  frames: number;
  atom_count: number;
  composition: string;
  xyz: string;
};

function load3Dmol(): Promise<void> {
  if (window.$3Dmol) {
    return Promise.resolve();
  }

  return new Promise((resolve, reject) => {
    const existing = document.querySelector<HTMLScriptElement>("script[data-3dmol]");
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener("error", () => reject(new Error("Failed to load 3Dmol")), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.src = "https://3Dmol.org/build/3Dmol-min.js";
    script.async = true;
    script.dataset["3dmol"] = "true";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load 3Dmol"));
    document.head.appendChild(script);
  });
}

function TaskStatus({ task }: { task: DemoTask }) {
  const metrics = [
    ["Queue", task.queue_state],
    ["Elapsed", task.elapsed],
    ["Step", `${task.current_step}/${task.total_steps}`],
    ["Progress", `${task.progress_percent}%`],
    ["Box", `${task.parameters.box_size_A} A`],
  ] as const;

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm" data-llm={`Viewing task ${task.task_id}, state ${task.state}, progress ${task.progress_percent}%`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-950">{task.run_name}</h2>
          <p className="text-xs text-slate-500">{task.task_id}</p>
        </div>
        <span className="rounded-full bg-teal-50 px-2.5 py-1 text-xs font-semibold text-teal-700">
          {task.state}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-sm sm:grid-cols-5">
        {metrics.map(([label, value]) => (
          <Metric key={label} label={label} value={value} />
        ))}
      </div>

      <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-100">
        <div className="h-full rounded-full bg-teal-600" style={{ width: `${task.progress_percent}%` }} />
      </div>

      {task.state === "RUNNING" && (
        <p className="mt-3 rounded-md bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-800">
          任务进行中
        </p>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
      <div className="text-[11px] font-semibold uppercase text-slate-500">{label}</div>
      <div className="mt-1 text-sm font-semibold text-slate-950">{value}</div>
    </div>
  );
}

function TaskListItem({
  task,
  isActive,
  onSelect,
}: {
  task: DemoTask;
  isActive: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      className={`rounded-md border px-3 py-2 text-left text-sm ${isActive ? "border-teal-700 bg-teal-50" : "border-slate-200 bg-white"}`}
      onClick={onSelect}
      data-llm={`Task ${task.task_id}: ${task.state}, ${task.progress_percent}%`}
    >
      <div className="font-semibold">{task.task_id}</div>
      <div className="text-xs text-slate-600">{task.state} · {task.progress_percent}%</div>
    </button>
  );
}

function TrajectoryViewer({ preview }: { preview?: TrajectoryPreview }) {
  const viewerRef = useRef<HTMLDivElement | null>(null);
  const viewerInstance = useRef<MoleculeViewer | null>(null);
  const [frame, setFrame] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [viewerReady, setViewerReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!preview || !viewerRef.current) {
      return;
    }

    let cancelled = false;
    setFrame(0);
    setIsPlaying(false);
    setViewerReady(false);
    setError(null);
    viewerInstance.current?.clear();
    viewerInstance.current = null;
    viewerRef.current.replaceChildren();

    load3Dmol()
      .then(() => {
        if (cancelled || !viewerRef.current || !window.$3Dmol) {
          return;
        }
        window.requestAnimationFrame(() => {
          if (cancelled || !viewerRef.current || !window.$3Dmol) {
            return;
          }
          const viewer = window.$3Dmol.createViewer(viewerRef.current);
          viewer.clear();
          viewer.addModelsAsFrames(preview.xyz, "xyz");
          viewer.setBackgroundColor("#101316");
          viewer.setStyle({ elem: "O" }, { sphere: { color: "#d94841", scale: 0.36 } });
          viewer.setStyle({ elem: "H" }, { sphere: { color: "#f8fafc", scale: 0.22 } });
          viewer.addStyle({}, { stick: { radius: 0.06, color: "#d9d6c7" } });
          viewerRef.current.querySelectorAll("canvas").forEach((canvas) => {
            canvas.style.position = "absolute";
            canvas.style.inset = "0";
            canvas.style.width = "100%";
            canvas.style.height = "100%";
            canvas.style.display = "block";
          });
          viewer.resize();
          viewer.zoomTo();
          viewer.render();
          viewerInstance.current = viewer;
          setViewerReady(true);
          setIsPlaying(preview.frames > 1);
          setError(null);
        });
      })
      .catch((err: Error) => {
        setViewerReady(false);
        setIsPlaying(false);
        setError(err.message);
      });

    return () => {
      cancelled = true;
      setIsPlaying(false);
      setViewerReady(false);
    };
  }, [preview]);

  useEffect(() => {
    if (!preview || !viewerReady || !isPlaying || preview.frames <= 1) {
      return;
    }
    const timer = window.setInterval(() => {
      setFrame((current) => (current + 1) % Math.max(1, preview.frames));
    }, 180);
    return () => window.clearInterval(timer);
  }, [isPlaying, preview, viewerReady]);

  useEffect(() => {
    const viewer = viewerInstance.current;
    if (!viewer || !preview) {
      return;
    }
    viewer.setFrame(frame);
    viewer.render();
  }, [frame, preview]);

  useEffect(() => {
    if (!viewerRef.current) {
      return;
    }
    const observer = new ResizeObserver(() => {
      viewerInstance.current?.resize();
      viewerInstance.current?.render();
    });
    observer.observe(viewerRef.current);
    return () => observer.disconnect();
  }, []);

  if (!preview) {
    return (
      <section className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
        Select the completed sample task to preview its trajectory.
      </section>
    );
  }

  return (
    <section className="min-w-0 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-base font-semibold text-slate-950">3D trajectory preview</h2>
          <p className="truncate text-xs text-slate-500" title={`${preview.path} · ${preview.atom_count} atoms · ${preview.composition}`}>
            {preview.path} · {preview.atom_count} atoms · {preview.composition}
          </p>
        </div>
        <span className="shrink-0 text-xs font-semibold text-slate-600" data-frame-counter>{frame + 1}/{preview.frames}</span>
      </div>
      <div
        ref={viewerRef}
        className="relative mt-3 h-[220px] max-h-[42vh] w-full overflow-hidden rounded-md bg-[#101316] sm:h-[280px]"
        style={{ contain: "layout paint size", cursor: "grab", touchAction: "none" }}
        aria-label="3D molecular trajectory preview"
      />
      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
      <div className="mt-3 flex items-center gap-3">
        <button
          className="h-8 rounded-md bg-teal-700 px-3 text-sm font-semibold text-white disabled:bg-slate-400"
          disabled={!viewerReady || Boolean(error) || preview.frames <= 1}
          onClick={() => setIsPlaying((current) => !current)}
        >
          {isPlaying ? "Pause" : "Play"}
        </button>
        <input
          className="min-w-0 flex-1 accent-teal-700"
          type="range"
          min="0"
          max={Math.max(0, preview.frames - 1)}
          value={frame}
          disabled={!viewerReady || Boolean(error)}
          onChange={(event) => {
            setIsPlaying(false);
            setFrame(Number(event.target.value));
          }}
        />
      </div>
    </section>
  );
}

export default function ManageDemoTasks() {
  const { output, responseMetadata } = useToolInfo<"manage_demo_tasks">();
  const { callTool, data, isPending } = useCallTool("submit_demo_task");
  const initialOutput = output as ToolOutput;
  const [tasks, setTasks] = useState<DemoTask[]>(initialOutput.tasks);
  const [activeTaskId, setActiveTaskId] = useState(initialOutput.active_task_id ?? initialOutput.tasks[0]?.task_id);
  const [temperature, setTemperature] = useState("240");
  const [pressure, setPressure] = useState("0.1");
  const [boxSize, setBoxSize] = useState("19");

  useEffect(() => {
    const task = data?.structuredContent.task as DemoTask | undefined;
    if (!task) {
      return;
    }
    setTasks((current) => [task, ...current.filter((item) => item.task_id !== task.task_id)]);
    setActiveTaskId(task.task_id);
  }, [data]);

  const activeTask = useMemo(
    () => tasks.find((task) => task.task_id === activeTaskId) ?? tasks[0],
    [activeTaskId, tasks],
  );
  const preview = responseMetadata?.trajectoryPreview as TrajectoryPreview | undefined;
  const showPreview = activeTask?.state === "COMPLETED" ? preview : undefined;

  return (
    <main className="grid gap-3 bg-[#f7f8f2] p-3 text-slate-950">
      <section key="submit-panel" className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-wrap items-end gap-3">
          <div key="intro" className="min-w-[160px] flex-1">
            <h1 className="text-lg font-semibold">vibematsci demo</h1>
            <p className="text-sm text-slate-600">Mock MD task submission and trajectory preview.</p>
          </div>
          <label key="temperature" className="grid gap-1 text-sm font-medium text-slate-700">
            Temperature K
            <input className="h-9 rounded-md border border-slate-300 px-2" value={temperature} onChange={(event) => setTemperature(event.target.value)} />
          </label>
          <label key="pressure" className="grid gap-1 text-sm font-medium text-slate-700">
            Pressure GPa
            <input className="h-9 rounded-md border border-slate-300 px-2" value={pressure} onChange={(event) => setPressure(event.target.value)} />
          </label>
          <label key="box-size" className="grid gap-1 text-sm font-medium text-slate-700">
            Box A
            <input className="h-9 rounded-md border border-slate-300 px-2" value={boxSize} onChange={(event) => setBoxSize(event.target.value)} />
          </label>
          <button
            key="submit"
            className="h-9 rounded-md bg-teal-700 px-4 text-sm font-semibold text-white disabled:bg-slate-400"
            disabled={isPending}
            onClick={() => callTool({
              temperature_K: Number(temperature),
              pressure_GPa: pressure.trim() === "" ? null : Number(pressure),
              box_size_A: Number(boxSize),
            })}
          >
            {isPending ? "Submitting" : "Submit mock task"}
          </button>
        </div>
      </section>

      <section key="task-workspace" className="grid min-w-0 gap-3 lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside key="task-list" className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
          <h2 key="task-list-heading" className="text-sm font-semibold text-slate-700">Tasks</h2>
          <div key="task-list-items" className="mt-2 grid gap-2">
            {tasks.map((task) => (
              <TaskListItem
                key={task.task_id}
                task={task}
                isActive={task.task_id === activeTask?.task_id}
                onSelect={() => setActiveTaskId(task.task_id)}
              />
            ))}
          </div>
        </aside>

        <div key="task-detail" className="grid min-w-0 gap-3">
          {activeTask && <TaskStatus key={`status-${activeTask.task_id}`} task={activeTask} />}
          <TrajectoryViewer key={`trajectory-${activeTask?.task_id ?? "none"}`} preview={showPreview} />
        </div>
      </section>
    </main>
  );
}
