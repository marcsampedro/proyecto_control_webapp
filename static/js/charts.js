// === Cargar plugin de anotaciones si no existe ===
if (typeof Chart !== "undefined") {
  Chart.register({
    id: "backgroundZone",
    beforeDraw(chart) {
      const { ctx, chartArea, scales } = chart;
      if (!chartArea || !scales?.y) return;
      const zeroY = scales.y.getPixelForValue(0);
      ctx.save();
      ctx.fillStyle = "rgba(255, 0, 0, 0.07)"; // sombra roja ligera debajo del 0
      ctx.fillRect(chartArea.left, zeroY, chartArea.right - chartArea.left, chartArea.bottom - zeroY);
      ctx.restore();
    },
  });
}

// === Función auxiliar para obtener todos los meses únicos ===
function unifyMonths(serieA, serieB) {
  const months = new Set();
  (serieA || []).forEach(r => months.add(r.mes));
  (serieB || []).forEach(r => months.add(r.mes));
  return Array.from(months).sort();
}

// === Función para alinear una serie con una lista de meses ===
function alignSeries(serie, months, keyMap) {
  const map = new Map(serie.map(r => [r.mes, r]));
  return months.map(m => {
    const row = map.get(m);
    const aligned = {};
    for (const [key, field] of Object.entries(keyMap)) {
      aligned[key] = row ? row[field] : null;
    }
    return aligned;
  });
}

// === Render Serie Mensual ===
function renderSerieChart(canvasId, serie, commonMonths) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || !Array.isArray(serie)) return;

  // Alinear datos
  const aligned = alignSeries(serie, commonMonths, {
    forecast: "forecast",
    facturado: "facturado",
    pdt_incurrir: "pdt_incurrir",
    inc_pdte_factura: "inc_pdte_factura",
    restante: "restante",
    new_forecast: "new_forecast",
    real_mas_deuda_pend: "real_mas_deuda_pend"
  });

  const datasets = [
    { label: "Forecast (1)", data: aligned.map(r => r.forecast), borderWidth: 2 },
    { label: "Facturado (2)", data: aligned.map(r => r.facturado), borderWidth: 2 },
    { label: "Pdt incurrir (3)", data: aligned.map(r => r.pdt_incurrir), borderWidth: 2 },
    { label: "Inc. pdte factura (4)", data: aligned.map(r => r.inc_pdte_factura), borderWidth: 2 },
    { label: "Restante ((2+3+4)-1)", data: aligned.map(r => r.restante), borderWidth: 2 },
    { label: "New Forecast", data: aligned.map(r => r.new_forecast), borderWidth: 2 },
    { label: "real + deuda pdte", data: aligned.map(r => r.real_mas_deuda_pend), borderWidth: 2 },
  ];

  new Chart(ctx, {
    type: "line",
    data: { labels: commonMonths, datasets },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      stacked: false,
      scales: {
        y: {
          beginAtZero: false,
          grid: {
            color: (ctx) => (ctx.tick.value === 0 ? "red" : "rgba(0,0,0,0.1)"), // línea 0 roja
          },
        },
      },
      plugins: {
        legend: { position: "bottom" },
      },
    },
  });
}

// === Render Evolución Bolsa ===
function renderEvoChart(canvasId, serie, commonMonths) {
  const ctx = document.getElementById(canvasId);
  if (!ctx || !Array.isArray(serie)) return;

  const aligned = alignSeries(serie, commonMonths, {
    incremento: "incremento",
    acumulado: "acumulado",
  });

  new Chart(ctx, {
    type: "line",
    data: {
      labels: commonMonths,
      datasets: [
        { label: "Incremento", data: aligned.map(r => r.incremento), borderWidth: 2 },
        { label: "Acumulado", data: aligned.map(r => r.acumulado), borderWidth: 2 },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      stacked: false,
      scales: {
        y: {
          beginAtZero: false,
          grid: {
            color: (ctx) => (ctx.tick.value === 0 ? "red" : "rgba(0,0,0,0.1)"), // línea 0 roja
          },
        },
      },
      plugins: {
        legend: { position: "bottom" },
      },
    },
  });
}

// === Render conjunto (usa meses unificados) ===
function renderDashboardCharts(serie, evo) {
  const months = unifyMonths(serie, evo);
  renderSerieChart("serieChart", serie, months);
  renderEvoChart("evoChart", evo, months);
}
