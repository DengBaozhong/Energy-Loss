const files = {
  eqe: null,
  seqe: null,
  eqeEl: null,
};

const fileInputs = {
  eqe: document.getElementById("eqeFile"),
  seqe: document.getElementById("seqeFile"),
  eqeEl: document.getElementById("eqeElFile"),
};

const fileLabels = {
  eqe: document.getElementById("eqeName"),
  seqe: document.getElementById("seqeName"),
  eqeEl: document.getElementById("eqeElName"),
};

const statusEl = document.getElementById("status");
const calculateBtn = document.getElementById("calculateBtn");
const saveCsvBtn = document.getElementById("saveCsvBtn");
const refreshBtn = document.getElementById("refreshBtn");
const resultsGrid = document.getElementById("resultsGrid");
const modeBadge = document.getElementById("modeBadge");
const chart = document.getElementById("lossChart");
const ctx = chart.getContext("2d");
let latestResults = null;

function setStatus(text, type = "") {
  statusEl.textContent = text;
  statusEl.className = `status ${type}`.trim();
}

function formatNumber(value, digits = 4) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const num = Number(value);
  if (Math.abs(num) > 0 && Math.abs(num) < 0.001) return num.toExponential(3);
  return num.toFixed(digits);
}

function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });
}

function bindDropzone(key) {
  const input = fileInputs[key];
  const zone = input.closest(".dropzone");
  const clearBtn = document.querySelector(`[data-clear="${key}"]`);

  function setFile(file) {
    files[key] = file;
    fileLabels[key].textContent = file ? file.name : key === "seqe" ? "Optional" : "Required";
    zone.classList.toggle("loaded", Boolean(file));
    clearBtn.disabled = !file;
  }

  input.addEventListener("change", () => {
    setFile(input.files[0] || null);
  });

  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("dragging");
  });

  zone.addEventListener("dragleave", () => zone.classList.remove("dragging"));

  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("dragging");
    setFile(event.dataTransfer.files[0] || null);
  });

  clearBtn.addEventListener("click", () => {
    input.value = "";
    setFile(null);
  });

  setFile(null);
}

Object.keys(fileInputs).forEach(bindDropzone);

function metric(label, value, unit = "", accent = false) {
  const card = document.createElement("div");
  card.className = `metric ${accent ? "accent" : ""}`.trim();
  card.innerHTML = `<span>${label}</span><strong>${value}${unit}</strong>`;
  return card;
}

function getCsvPrefix() {
  const raw = document.getElementById("csvPrefix").value.trim() || "energy_loss";
  return raw.replace(/[<>:"/\\|?*\x00-\x1f]/g, "_");
}

function toCsvValue(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  if (/[",\n\r]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

function buildResultsCsv(results) {
  const rows = Object.entries(results).map(([key, value]) => [key, value]);
  return ["parameter,value", ...rows.map((row) => row.map(toCsvValue).join(","))].join("\n");
}

function resetResults() {
  latestResults = null;
  window.lastResults = null;
  resultsGrid.innerHTML = '<div class="empty">Run a calculation to view parameters.</div>';
  modeBadge.textContent = "No calculation";
  saveCsvBtn.disabled = true;
  ctx.clearRect(0, 0, chart.width, chart.height);
  setStatus("Waiting for spectra.");
}

function renderResults(results) {
  resultsGrid.innerHTML = "";
  const cards = [
    metric("Eg", formatNumber(results.Eg_eV), " eV"),
    metric("VocSQ", formatNumber(results.Voc_SQ_V), " V"),
    metric("EQEEL at Jsc", formatNumber(results.EQE_EL_at_Jsc), ""),
    metric("Jsc", formatNumber(results.Jsc_rad_mA_cm2), " mA cm^-2"),
    metric("E1", formatNumber(results.E1_eV), " eV", true),
    metric("E2", formatNumber(results.E2_eV), " eV", true),
    metric("E3", formatNumber(results.E3_eV), " eV", true),
    metric("E1 + E2 + E3", formatNumber(results.E_loss_total_eV), " eV"),
  ];

  if (results.Voc_input_V !== undefined) {
    cards.push(metric("Voc", formatNumber(results.Voc_input_V), " V"));
    cards.push(metric("VocSQ - Voc", formatNumber(results.VocSQ_minus_Voc_eV), " eV"));
    cards.push(metric("E2 + E3", formatNumber(results.E2_plus_E3_eV), " eV"));
    cards.push(metric("Difference", formatNumber(results.VocSQVoc_minus_E2E3_eV), " eV"));
  }

  cards.forEach((card) => resultsGrid.appendChild(card));
  modeBadge.textContent = results.sEQE && results.sEQE !== "not used" ? "EQE + FTPS-EQE" : "EQE only";
  saveCsvBtn.disabled = false;
}

function resizeCanvas() {
  const rect = chart.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  chart.width = Math.max(1, Math.floor(rect.width * dpr));
  chart.height = Math.max(1, Math.floor(rect.height * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function drawChart(results) {
  resizeCanvas();
  const rect = chart.getBoundingClientRect();
  const width = rect.width;
  const height = rect.height;
  ctx.clearRect(0, 0, width, height);

  const bars = [
    { label: "E1", value: results.E1_eV, color: "#3b82f6" },
    { label: "E2", value: results.E2_eV, color: "#ff4d4f" },
    { label: "E3", value: results.E3_eV, color: "#d65a31" },
  ];

  if (results.Voc_input_V !== undefined) {
    bars.push({ label: "VocSQ-Voc", value: results.VocSQ_minus_Voc_eV, color: "#bdd0ea" });
    bars.push({ label: "E2+E3", value: results.E2_plus_E3_eV, color: "#a7f3d0" });
  }

  const padding = { left: 76, right: 28, top: 38, bottom: 70 };
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;
  const maxValue = Math.max(...bars.map((bar) => Number(bar.value) || 0), 0.1);
  const yMax = Math.ceil(maxValue * 12) / 10;

  ctx.fillStyle = "#0f141b";
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = "#303846";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#9aa8bb";
  ctx.font = "16px Inter, Segoe UI, Arial";
  ctx.textAlign = "right";
  ctx.textBaseline = "middle";

  for (let i = 0; i <= 5; i += 1) {
    const value = (yMax / 5) * i;
    const y = padding.top + plotH - (value / yMax) * plotH;
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(width - padding.right, y);
    ctx.stroke();
    ctx.fillText(value.toFixed(2), padding.left - 10, y);
  }

  ctx.strokeStyle = "#3b4658";
  ctx.beginPath();
  ctx.moveTo(padding.left, padding.top);
  ctx.lineTo(padding.left, padding.top + plotH);
  ctx.lineTo(width - padding.right, padding.top + plotH);
  ctx.stroke();

  ctx.save();
  ctx.translate(24, padding.top + plotH / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillStyle = "#e8edf5";
  ctx.textAlign = "center";
  ctx.font = "17px Inter, Segoe UI, Arial";
  ctx.fillText("Energy loss (eV)", 0, 0);
  ctx.restore();

  const gap = Math.max(16, plotW / bars.length * 0.28);
  const barW = Math.max(34, (plotW - gap * (bars.length + 1)) / bars.length);

  bars.forEach((bar, index) => {
    const x = padding.left + gap + index * (barW + gap);
    const barH = (Number(bar.value) / yMax) * plotH;
    const y = padding.top + plotH - barH;

    ctx.fillStyle = bar.color;
    ctx.fillRect(x, y, barW, barH);

    ctx.fillStyle = "#f8fafc";
    ctx.font = "17px Inter, Segoe UI, Arial";
    ctx.textAlign = "center";
    ctx.textBaseline = "bottom";
    ctx.fillText(formatNumber(bar.value, 3), x + barW / 2, y - 10);

    ctx.fillStyle = "#bdd0ea";
    ctx.textBaseline = "top";
    ctx.fillText(bar.label, x + barW / 2, padding.top + plotH + 18);
  });
}

async function calculate() {
  if (!files.eqe || !files.eqeEl) {
    setStatus("Upload EQE and EQE_EL files before calculation.", "error");
    return;
  }

  calculateBtn.disabled = true;
  setStatus("Calculating...");

  try {
    const payload = {
      files: {
        eqe: await readFile(files.eqe),
        seqe: files.seqe ? await readFile(files.seqe) : null,
        eqeEl: await readFile(files.eqeEl),
      },
      params: {
        eqeRangeNm: document.getElementById("eqeRange").value,
        elCurrent: document.getElementById("elCurrent").value,
        temperature: document.getElementById("temperature").value,
        voc: document.getElementById("voc").value,
      },
    };

    const response = await fetch("/api/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!data.ok) throw new Error(data.error || "Calculation failed.");

    renderResults(data.results);
    drawChart(data.results);
    latestResults = data.results;
    setStatus("Calculation complete.", "ok");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    calculateBtn.disabled = false;
  }
}

async function saveCsv() {
  if (!latestResults) {
    setStatus("Run a calculation before saving CSV.", "error");
    return;
  }

  const filename = `${getCsvPrefix()}_results.csv`;
  const blob = new Blob([buildResultsCsv(latestResults)], { type: "text/csv;charset=utf-8" });

  try {
    if ("showSaveFilePicker" in window) {
      const handle = await window.showSaveFilePicker({
        suggestedName: filename,
        types: [{ description: "CSV file", accept: { "text/csv": [".csv"] } }],
      });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
    } else {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.click();
      URL.revokeObjectURL(url);
    }
    setStatus("CSV saved.", "ok");
  } catch (error) {
    if (error.name !== "AbortError") setStatus(error.message, "error");
  }
}

calculateBtn.addEventListener("click", calculate);
saveCsvBtn.addEventListener("click", saveCsv);
refreshBtn.addEventListener("click", resetResults);
window.addEventListener("resize", () => {
  const hasResults = resultsGrid.querySelector(".metric");
  if (hasResults && window.lastResults) drawChart(window.lastResults);
});

const originalDrawChart = drawChart;
drawChart = (results) => {
  window.lastResults = results;
  originalDrawChart(results);
};
