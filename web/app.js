const trajSelect = document.querySelector("#trajSelect");
const strideInput = document.querySelector("#strideInput");
const maxFramesInput = document.querySelector("#maxFramesInput");
const loadButton = document.querySelector("#loadButton");
const playButton = document.querySelector("#playButton");
const frameSlider = document.querySelector("#frameSlider");
const frameLabel = document.querySelector("#frameLabel");
const statusEl = document.querySelector("#status");
const metaEl = document.querySelector("#meta");
const viewerEl = document.querySelector("#viewer");

let viewer;
let frameCount = 0;
let currentFrame = 0;
let timer = null;

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.dataset.error = isError ? "true" : "false";
}

function setPlayback(enabled) {
  playButton.disabled = !enabled;
  frameSlider.disabled = !enabled;
  if (!enabled) {
    stopPlayback();
  }
}

function stopPlayback() {
  if (timer !== null) {
    window.clearInterval(timer);
    timer = null;
  }
  playButton.textContent = "Play";
}

function showFrame(index) {
  if (!viewer || frameCount === 0) {
    return;
  }
  currentFrame = Math.max(0, Math.min(frameCount - 1, index));
  viewer.setFrame(currentFrame);
  viewer.render();
  frameSlider.value = String(currentFrame);
  frameLabel.textContent = `Frame ${currentFrame + 1} / ${frameCount}`;
}

function togglePlayback() {
  if (timer !== null) {
    stopPlayback();
    return;
  }
  playButton.textContent = "Pause";
  timer = window.setInterval(() => {
    const next = (currentFrame + 1) % frameCount;
    showFrame(next);
  }, 120);
}

function styleViewer() {
  viewer.setBackgroundColor("#101316");
  viewer.setStyle({ elem: "O" }, { sphere: { color: "#d94841", scale: 0.36 } });
  viewer.setStyle({ elem: "H" }, { sphere: { color: "#f7f7f0", scale: 0.22 } });
  viewer.addStyle({}, { stick: { radius: 0.06, color: "#d9d6c7" } });
  viewer.zoomTo();
  viewer.render();
}

async function loadFiles() {
  const response = await fetch("/api/files");
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Failed to list trajectories");
  }
  trajSelect.replaceChildren();
  for (const file of data.files) {
    const option = document.createElement("option");
    option.value = file.path;
    option.textContent = `${file.path} (${(file.size_bytes / 1024 / 1024).toFixed(1)} MB)`;
    trajSelect.append(option);
  }
  if (data.files.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = "No .traj files found";
    trajSelect.append(option);
    loadButton.disabled = true;
    setStatus("No .traj files found under the vibematsci directory.", true);
    return;
  }
  setStatus("Trajectory list ready.");
}

async function loadTrajectory() {
  const path = trajSelect.value;
  if (!path) {
    return;
  }
  setPlayback(false);
  setStatus(`Reading ${path}...`);
  metaEl.textContent = "";
  frameLabel.textContent = "Frame 0 / 0";
  frameSlider.value = "0";
  loadButton.disabled = true;

  try {
    const query = new URLSearchParams({
      path,
      stride: strideInput.value,
      max_frames: maxFramesInput.value,
    });
    const response = await fetch(`/api/trajectory?${query.toString()}`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Failed to load trajectory");
    }

    viewer = $3Dmol.createViewer(viewerEl);
    viewer.clear();
    viewer.addModelsAsFrames(data.xyz, "xyz");
    frameCount = data.frames;
    frameSlider.max = String(Math.max(0, frameCount - 1));
    currentFrame = 0;
    styleViewer();
    showFrame(0);
    setPlayback(frameCount > 1);

    const composition = Object.entries(data.symbols)
      .map(([symbol, count]) => `${symbol}${count}`)
      .join(" ");
    const truncated = data.truncated ? " · truncated" : "";
    metaEl.textContent = `${data.atom_count} atoms · ${composition} · stride ${data.stride}${truncated}`;
    setStatus(`Loaded ${data.frames} frame${data.frames === 1 ? "" : "s"} from ${data.path}.`);
  } catch (error) {
    setStatus(error instanceof Error ? error.message : String(error), true);
  } finally {
    loadButton.disabled = false;
  }
}

loadButton.addEventListener("click", loadTrajectory);
playButton.addEventListener("click", togglePlayback);
frameSlider.addEventListener("input", () => {
  stopPlayback();
  showFrame(Number(frameSlider.value));
});
window.addEventListener("resize", () => {
  if (viewer) {
    viewer.resize();
    viewer.render();
  }
});

try {
  await loadFiles();
  await loadTrajectory();
} catch (error) {
  setStatus(error instanceof Error ? error.message : String(error), true);
}
