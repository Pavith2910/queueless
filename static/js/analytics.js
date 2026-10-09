// analytics.js - fetches analytics APIs and draws charts with Chart.js
const COLORS = ["#ffb547", "#3ddc97", "#6ea8fe", "#ff6b6b", "#c792ea", "#5eead4"];
const HOURS = Array.from({ length: 15 }, (_, i) => i + 7);   // 7 am .. 9 pm
const WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const charts = {};

Chart.defaults.color = "#8b93a3";
Chart.defaults.borderColor = "#23262f";
Chart.defaults.font.family = "Inter, sans-serif";

const $ = (id) => document.getElementById(id);
const hourLabel = (h) => `${h % 12 || 12}${h < 12 ? "am" : "pm"}`;
const fmt = (n) => Number(n).toLocaleString("en-IN");

async function getJSON(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) throw new Error(`${url} returned ${res.status}`);
  return res.json();
}

function drawChart(id, config) {
  if (charts[id]) charts[id].destroy();     // replace old chart when reloading
  charts[id] = new Chart($(id), config);
}

async function loadOverview() {
  const o = await getJSON("/api/analytics/overview");
  $("t-events").textContent = fmt(o.events);
  $("t-served").textContent = fmt(o.served);
  $("t-wait").textContent = o.avg_actual_wait_min !== null ? `${o.avg_actual_wait_min} min` : "–";
  $("t-days").textContent = o.days_of_history;

  const when = o.metrics.computed_at
    ? new Date(o.metrics.computed_at).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })
    : "never";
  $("metrics-info").textContent = `${fmt(o.metrics.documents)} metric documents · computed at ${when}`;

  $("busiest").innerHTML = o.busiest_slots.map((s) => `
    <li>
      <div><strong>${s.name}</strong><small>${s.day} · ${hourLabel(s.hour)}–${hourLabel(s.hour + 1)}</small></div>
      <span>${s.avg_waiting.toFixed(1)}<small>avg waiting</small></span>
    </li>`).join("");

  const byDay = Object.fromEntries(o.served_by_weekday.map((d) => [d.day, d.avg_served]));
  drawChart("weekday-chart", {
    type: "bar",
    data: {
      labels: WEEK,
      datasets: [{ data: WEEK.map((d) => byDay[d] ?? 0), backgroundColor: "#ffb547", borderRadius: 6 }],
    },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false } } },
  });
}

async function loadHourly() {
  const data = await getJSON("/api/analytics/hourly");
  drawChart("hourly-chart", {
    type: "line",
    data: {
      labels: HOURS.map(hourLabel),
      datasets: data.map((loc, i) => {
        const byHour = Object.fromEntries(loc.hours.map((h) => [h.hour, h.avg]));
        const color = COLORS[i % COLORS.length];
        return {
          label: loc.name,
          data: HOURS.map((h) => byHour[h] ?? null),
          borderColor: color, backgroundColor: color,
          tension: 0.35, pointRadius: 2, borderWidth: 2,
        };
      }),
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: { y: { beginAtZero: true, title: { display: true, text: "people waiting (avg)" } } },
    },
  });

  $("peak-chips").innerHTML = data.map((loc, i) => `
    <span class="chip"><i style="background:${COLORS[i % COLORS.length]}"></i>
      ${loc.name}: peak ${hourLabel(loc.peak_hour)} (${loc.peak_avg} avg)</span>`).join("");
  return data;
}

async function loadSpeed() {
  const data = await getJSON("/api/analytics/service-speed");
  drawChart("speed-chart", {
    type: "bar",
    data: {
      labels: data.map((d) => d.name),
      datasets: [
        { label: "Fastest to slowest", data: data.map((d) => [d.min, d.max]),
          backgroundColor: "rgba(110,168,254,0.25)", borderRadius: 6 },
        { label: "Average", data: data.map((d) => d.avg),
          backgroundColor: "#6ea8fe", borderRadius: 6 },
      ],
    },
    options: {
      indexAxis: "y",
      maintainAspectRatio: false,
      scales: { y: { stacked: true }, x: { title: { display: true, text: "seconds" } } },
    },
  });
}

async function loadHeatmap(id) {
  const cells = await getJSON(`/api/analytics/heatmap/${id}`);
  const max = Math.max(1, ...cells.map((c) => c.avg_waiting));
  const lookup = {};
  cells.forEach((c) => { lookup[`${c.day}-${c.hour}`] = c; });

  let html = `<div class="hm-row hm-head"><span></span>${HOURS.map((h) =>
    `<span>${h % 3 === 0 ? hourLabel(h) : ""}</span>`).join("")}</div>`;
  for (const day of WEEK) {
    html += `<div class="hm-row"><span class="hm-day">${day}</span>`;
    for (const h of HOURS) {
      const c = lookup[`${day}-${h}`];
      if (!c) {
        html += `<span class="hm-cell empty" title="${day} ${hourLabel(h)}: closed / no data"></span>`;
        continue;
      }
      const alpha = 0.08 + 0.92 * (c.avg_waiting / max);
      html += `<span class="hm-cell" style="background:rgba(255,181,71,${alpha.toFixed(2)})"
        title="${day} ${hourLabel(h)}: ${c.avg_waiting.toFixed(1)} avg waiting (max ${c.max_waiting})"></span>`;
    }
    html += `</div>`;
  }
  $("heatmap").innerHTML = html;
}

async function loadForecast(id) {
  const f = await getJSON(`/api/analytics/forecast/${id}`);
  if (f.closed_today || !f.slots.length) {
    $("forecast-text").innerHTML = `${f.name} is closed today (${f.day}).`;
  } else if (f.best_hour === null) {
    $("forecast-text").innerHTML = `${f.name} is closed for the rest of today.`;
  } else {
    $("forecast-text").innerHTML = `Based on past ${f.day}s, the shortest wait at
      <strong>${f.name}</strong> is around <strong>${hourLabel(f.best_hour)}</strong>
      (~${f.best_wait_min} min).`;
  }
  drawChart("forecast-chart", {
    type: "bar",
    data: {
      labels: f.slots.map((s) => hourLabel(s.hour)),
      datasets: [{
        label: "Expected wait (min)",
        data: f.slots.map((s) => s.expected_wait_min),
        backgroundColor: f.slots.map((s) =>
          s.hour === f.best_hour ? "#3ddc97" : s.is_past ? "#2b2f3a" : "#ffb547"),
        borderRadius: 6,
      }],
    },
    options: {
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { beginAtZero: true, title: { display: true, text: "minutes" } } },
    },
  });
}

async function loadLocation(id) {
  await Promise.all([loadHeatmap(id), loadForecast(id)]);
}

async function init() {
  try {
    await loadOverview();                      // also makes sure the cache is fresh
    const [locations] = await Promise.all([loadHourly(), loadSpeed()]);
    const select = $("loc-select");
    const current = select.value || "CANTEEN_A";
    select.innerHTML = locations.map((l) =>
      `<option value="${l.location_id}">${l.name}</option>`).join("");
    select.value = current;
    await loadLocation(current);
  } catch (err) {
    console.error(err);
    alert("Could not load analytics: " + err.message);
  }
}

$("loc-select").addEventListener("change", (e) => loadLocation(e.target.value));

$("refresh-btn").addEventListener("click", async () => {
  const btn = $("refresh-btn");
  btn.disabled = true;
  btn.textContent = "Recomputing…";
  const r = await getJSON("/api/analytics/refresh", { method: "POST" });
  btn.textContent = `Done: ${fmt(r.documents)} docs in ${r.ms} ms`;
  await init();
  setTimeout(() => { btn.textContent = "Recompute metrics"; btn.disabled = false; }, 3000);
});

init();