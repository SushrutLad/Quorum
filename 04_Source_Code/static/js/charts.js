// Small helpers so every page draws charts the same way (uses Chart.js).
const UTILITY_COLORS = { Electricity: "#2a78d6", Water: "#1baf7a", Gas: "#eb6834" };
const CATEGORY_COLORS = ["#2a78d6", "#eb6834", "#1baf7a"];

if (window.Chart) {
  Chart.defaults.font.family = '"Segoe UI", system-ui, Roboto, Arial, sans-serif';
  Chart.defaults.color = "#64748b";
  Chart.defaults.maintainAspectRatio = false;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.boxHeight = 8;
}

const rupees = (v) => "₹" + Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 });

function monthLabel(ym) {
  const [y, m] = ym.split("-");
  return new Date(y, m - 1, 1).toLocaleString("en-IN", { month: "short" });
}

// series: { "Electricity": [..], "Water": [..] }  -> one line per utility
function lineChart(canvasId, months, series, money = true) {
  new Chart(document.getElementById(canvasId), {
    type: "line",
    data: {
      labels: months.map(monthLabel),
      datasets: Object.entries(series).map(([name, values]) => ({
        label: name, data: values, borderColor: UTILITY_COLORS[name], backgroundColor: UTILITY_COLORS[name],
        borderWidth: 2, pointRadius: 4, tension: 0.3,
      })),
    },
    options: {
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "top", align: "start" },
                 tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${money ? rupees(c.raw) : c.raw}` } } },
      scales: { y: { beginAtZero: true, grid: { color: "#eef1f5" }, ticks: { callback: (v) => (money ? rupees(v) : v) } },
                x: { grid: { display: false } } },
    },
  });
}

function barChart(canvasId, labels, values, color, unit = "", horizontal = false) {
  new Chart(document.getElementById(canvasId), {
    type: "bar",
    data: { labels, datasets: [{ data: values, backgroundColor: color, borderRadius: 4, maxBarThickness: 36 }] },
    options: {
      indexAxis: horizontal ? "y" : "x",
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${c.raw} ${unit}` } } },
      scales: { x: { grid: { display: horizontal }, beginAtZero: true }, y: { grid: { color: "#eef1f5" }, beginAtZero: true } },
    },
  });
}

// Grouped bars per month, one colour per utility (all values in rupees)
function groupedBars(canvasId, months, series) {
  new Chart(document.getElementById(canvasId), {
    type: "bar",
    data: {
      labels: months.map(monthLabel),
      datasets: Object.entries(series).map(([name, values]) => ({
        label: name, data: values, backgroundColor: UTILITY_COLORS[name], borderRadius: 4, maxBarThickness: 18,
      })),
    },
    options: {
      plugins: { legend: { position: "top", align: "start" },
                 tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${rupees(c.raw)}` } } },
      scales: { y: { beginAtZero: true, grid: { color: "#eef1f5" }, ticks: { callback: rupees } }, x: { grid: { display: false } } },
    },
  });
}

function doughnut(canvasId, labels, values, colors) {
  new Chart(document.getElementById(canvasId), {
    type: "doughnut",
    data: { labels, datasets: [{ data: values, backgroundColor: colors, borderColor: "#fff", borderWidth: 2 }] },
    options: {
      cutout: "62%",
      plugins: { legend: { position: "bottom" }, tooltip: { callbacks: { label: (c) => `${c.label}: ${rupees(c.raw)}` } } },
    },
  });
}
