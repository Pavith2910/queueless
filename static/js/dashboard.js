// dashboard.js - the student-facing live dashboard
const REFRESH_MS = 10000;
const ICONS = { canteen: "🍽️", office: "📄", library: "📚", clinic: "🏥" };
const STATUS_TEXT = { low: "Short queue", moderate: "Moderate", busy: "Busy", closed: "Closed" };
const TREND_TEXT = { rising: "↗ Queue growing", falling: "↘ Queue shrinking", steady: "→ Steady" };
const VERDICT_TEXT = { switch: "Switch", stay: "Stay", none: "No option" };

const state = { queues: [], filter: "all", sort: "wait", demoTime: null, firstLoad: true };

const $ = (id) => document.getElementById(id);
const pretty = (s) => String(s).replaceAll("_", " ");
const hourLabel = (h) => `${h % 12 || 12}${h < 12 ? "am" : "pm"}`;
const fmtMin = (m) => (m >= 10 ? Math.round(m) : Math.round(m * 10) / 10);
const cmp = (a, b) => (a === b ? 0 : a < b ? -1 : 1);

function ago(minutes) {
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)} h ago`;
  return `${Math.floor(minutes / 1440)} d ago`;
}

/* ---------- card pieces ---------- */
function ring(q) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const frac = q.is_open ? Math.min(q.est_wait_min / 30, 1) : 0;   // full ring = 30 min
  return `
    <svg class="ring" viewBox="0 0 80 80">
      <circle cx="40" cy="40" r="${r}" class="ring-bg"/>
      <circle cx="40" cy="40" r="${r}" class="ring-fg"
        stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${(c * (1 - frac)).toFixed(1)}"/>
    </svg>
    <div class="ring-text">
      <strong>${q.is_open ? fmtMin(q.est_wait_min) : "–"}</strong>
      <small>${q.is_open ? "min wait" : "closed"}</small>
    </div>`;
}

function peopleRow(q) {
  if (!q.is_open) {
    return `<div class="people"><span>Open ${q.opening_hours.open}–${q.opening_hours.close}</span></div>`;
  }
  const shown = Math.min(q.waiting, 18);
  const figures = "<i></i>".repeat(shown);
  const more = q.waiting > shown ? `<b>+${q.waiting - shown}</b>` : "";
  const label = q.waiting === 0 ? "No queue right now" : `${q.waiting} waiting`;
  return `<div class="people">${figures}${more}<span>${label}</span></div>`;
}

function sparkline(trend) {
  if (trend.length < 2) return `<span class="spark-empty">no recent updates</span>`;
  const w = 120, h = 32;
  const max = Math.max(1, ...trend.map((p) => p.w));
  const points = trend.map((p, i) => {
    const x = (i / (trend.length - 1)) * w;
    const y = h - (p.w / max) * (h - 4) - 2;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none"><polyline points="${points}"/></svg>`;
}

function extraTags(extras) {
  // Shows category-specific fields - the flexible schema, visible to users
  const tags = [];
  for (const [key, value] of Object.entries(extras)) {
    if (key === "menu_tags") value.forEach((v) => tags.push(pretty(v)));
    else if (Array.isArray(value)) tags.push(`${pretty(key)}: ${value.map(pretty).join(", ")}`);
    else if (typeof value === "boolean") { if (value) tags.push(pretty(key)); }
    else tags.push(`${pretty(key)}: ${value}`);
  }
  return tags.slice(0, 5).map((t) => `<span class="tag">${t}</span>`).join("");
}

function cardHTML(q) {
  return `
  <article class="qcard s-${q.status}" data-id="${q.location_id}" tabindex="0">
    <header>
      <span class="icon">${ICONS[q.category] || "📍"}</span>
      <div class="title">
        <h3>${q.name}</h3>
        <small>${pretty(q.category)} · ${q.opening_hours.open}–${q.opening_hours.close}</small>
      </div>
      <span class="pill pill-${q.status}">${STATUS_TEXT[q.status]}</span>
    </header>
    <div class="qcard-main">
      <div class="ring-wrap">${ring(q)}</div>
      <div class="qcard-stats">
        <div><strong>${q.waiting}</strong><small>people</small></div>
        <div><strong>${q.counters}</strong><small>counters</small></div>
        <div><strong>${q.avg_service_seconds}s</strong><small>per person</small></div>
      </div>
    </div>
    ${peopleRow(q)}
    <div class="qcard-trend">
      <span class="trend t-${q.trend_direction}">${TREND_TEXT[q.trend_direction]}</span>
      ${sparkline(q.trend)}
    </div>
    <div class="tags">${extraTags(q.extras)}</div>
    <footer><small>Updated ${ago(q.minutes_since_update)}</small><small class="more">Details →</small></footer>
  </article>`;
}

/* ---------- rendering ---------- */
function renderCards() {
  const waitKey = (q) => (q.is_open ? q.est_wait_min : Infinity);
  const list = state.queues.filter((q) => state.filter === "all" || q.category === state.filter);
  if (state.sort === "name") list.sort((a, b) => a.name.localeCompare(b.name));
  if (state.sort === "wait") list.sort((a, b) => cmp(waitKey(a), waitKey(b)));
  if (state.sort === "busy") list.sort((a, b) => cmp(q2(b), q2(a)));
  function q2(q) { return q.is_open ? q.est_wait_min : -1; }

  const box = $("cards");
  box.innerHTML = list.map(cardHTML).join("") || `<p class="muted">No locations in this category.</p>`;
  if (state.firstLoad) {
    box.classList.add("animate");                 // entrance animation only once
    setTimeout(() => box.classList.remove("animate"), 800);
  }
}

function renderSummary() {
  const open = state.queues.filter((q) => q.is_open);
  $("s-open").textContent = `${open.length}/${state.queues.length}`;
  $("s-waiting").textContent = open.reduce((sum, q) => sum + q.waiting, 0);
  if (!open.length) {
    $("s-shortest").textContent = $("s-longest").textContent = "–";
    $("s-shortest-name").textContent = $("s-longest-name").textContent = "everything is closed";
    return;
  }
  const sorted = [...open].sort((a, b) => a.est_wait_min - b.est_wait_min);
  const shortest = sorted[0];
  const longest = sorted[sorted.length - 1];
  $("s-shortest").textContent = `${fmtMin(shortest.est_wait_min)} min`;
  $("s-shortest-name").textContent = `shortest · ${shortest.name}`;
  $("s-longest").textContent = `${fmtMin(longest.est_wait_min)} min`;
  $("s-longest-name").textContent = `longest · ${longest.name}`;
}

function tickClock() {
  if (state.demoTime) {
    $("clock").textContent = state.demoTime;
  } else {
    $("clock").textContent = new Date().toLocaleTimeString("en-IN", {
      hour: "2-digit", minute: "2-digit", timeZone: "Asia/Kolkata",
    });
  }
  $("demo-badge").hidden = !state.demoTime;
}

function restartProgress() {
  const bar = $("refresh-progress");
  bar.style.animation = "none";
  void bar.offsetWidth;                            // forces the animation to restart
  bar.style.animation = `fill ${REFRESH_MS}ms linear forwards`;
}

async function load() {
  try {
    const res = await fetch("/api/queues");
    const data = await res.json();
    state.queues = data.queues;
    state.demoTime = data.demo_time;
    renderSummary();
    renderCards();
    fillAdvisorLocations();
    tickClock();
    restartProgress();
    state.firstLoad = false;
  } catch (err) {
    $("cards").innerHTML = `<p class="error">Could not load queues. Is the server running?</p>`;
  }
}

/* ---------- "Where should I go?" advisor ---------- */
function fillAdvisorLocations() {
  const select = $("adv-location");
  if (select.options.length) return;               // fill only once
  select.innerHTML = state.queues
    .map((q) => `<option value="${q.location_id}">${q.name}</option>`).join("");
  fillServices();
}

function fillServices() {
  const q = state.queues.find((x) => x.location_id === $("adv-location").value);
  $("adv-service").innerHTML = `<option value="">Anything they offer</option>` +
    q.services.map((s) => `<option value="${s}">${pretty(s)}</option>`).join("");
}

async function runAdvisor() {
  const id = $("adv-location").value;
  const service = $("adv-service").value;
  const url = `/api/recommend/${id}` + (service ? `?service=${encodeURIComponent(service)}` : "");
  const box = $("adv-result");
  box.innerHTML = `<p class="muted">Comparing…</p>`;

  const res = await fetch(url);
  const r = await res.json();
  if (!res.ok) { box.innerHTML = `<p class="error">${r.error}</p>`; return; }

  const rows = [];
  if (r.origin.is_open) {
    rows.push({ name: `${r.origin.name} (planned)`, walk: 0, wait: r.origin.est_wait_min });
  }
  r.options.forEach((o) => rows.push({
    name: o.name, walk: o.walk_min, wait: o.est_wait_min,
    best: r.recommended && o.location_id === r.recommended.location_id,
  }));
  const max = Math.max(1, ...rows.map((x) => x.walk + x.wait));

  const bars = rows.map((x) => `
    <div class="cmp-row ${x.best ? "best" : ""}">
      <div class="cmp-label">${x.name}<small>${fmtMin(x.walk + x.wait)} min total</small></div>
      <div class="cmp-bar">
        <i class="walk" style="width:${(x.walk / max) * 100}%"></i>
        <i class="wait" style="width:${(x.wait / max) * 100}%"></i>
      </div>
    </div>`).join("");

  box.innerHTML = `
    <div class="verdict v-${r.verdict}">
      <span>${VERDICT_TEXT[r.verdict]}</span>
      <p>${r.message}</p>
    </div>
    ${rows.length ? `<div class="compare">${bars}
      <div class="cmp-legend"><span><i class="walk"></i>walking</span><span><i class="wait"></i>waiting</span></div>
    </div>` : ""}`;
}

/* ---------- detail drawer ---------- */
async function openDrawer(id) {
  const [q, f] = await Promise.all([
    fetch(`/api/queues/${id}`).then((r) => r.json()),
    fetch(`/api/analytics/forecast/${id}`).then((r) => r.json()),
  ]);

  let bestText;
  if (f.best_hour !== null) bestText = `Best time today: <strong>${hourLabel(f.best_hour)}</strong> (~${fmtMin(f.best_wait_min)} min wait)`;
  else bestText = f.closed_today ? "Closed today." : "Closed for the rest of today.";
  const maxWait = Math.max(1, ...f.slots.map((s) => s.expected_wait_min));
  const avgSvc = q.today.avg_service_seconds ? `${q.today.avg_service_seconds}s` : "–";

  $("drawer-body").innerHTML = `
    <p class="eyebrow">${ICONS[q.category] || ""} ${pretty(q.category)}</p>
    <h2>${q.name}</h2>
    <span class="pill pill-${q.status}">${STATUS_TEXT[q.status]}</span>
    <div class="drawer-stats">
      <div><strong>${q.is_open ? fmtMin(q.est_wait_min) : "–"}</strong><small>min wait now</small></div>
      <div><strong>${q.today.served}</strong><small>served today</small></div>
      <div><strong>${q.today.peak_waiting}</strong><small>longest queue today</small></div>
      <div><strong>${avgSvc}</strong><small>avg service today</small></div>
    </div>
    <h4>A typical ${f.day} here</h4>
    <p class="muted small">${bestText}</p>
    <div class="mini-bars">${f.slots.map((s) => `
      <div class="mb ${s.hour === f.best_hour ? "best" : ""} ${s.is_past ? "past" : ""}"
           title="${hourLabel(s.hour)}: ~${s.expected_wait_min} min">
        <i style="height:${Math.max(4, (s.expected_wait_min / maxWait) * 100)}%"></i>
        <small>${s.hour % 2 === 0 ? hourLabel(s.hour) : ""}</small>
      </div>`).join("")}</div>
    <h4>Services</h4>
    <div class="tags">${q.services.map((s) => `<span class="tag">${pretty(s)}</span>`).join("")}</div>
    <button id="drawer-compare" class="btn btn-primary">Find a shorter queue</button>`;

  $("drawer").hidden = false;
  $("drawer-compare").onclick = () => {
    $("adv-location").value = id;
    fillServices();
    closeDrawer();
    runAdvisor();
    $("adv-btn").scrollIntoView({ behavior: "smooth", block: "center" });
  };
}

function closeDrawer() { $("drawer").hidden = true; }

/* ---------- events ---------- */
$("filters").addEventListener("click", (e) => {
  const btn = e.target.closest(".filter");
  if (!btn) return;
  document.querySelectorAll(".filter").forEach((b) => b.classList.toggle("active", b === btn));
  state.filter = btn.dataset.cat;
  renderCards();
});

$("sort").addEventListener("change", (e) => { state.sort = e.target.value; renderCards(); });

$("cards").addEventListener("click", (e) => {
  const card = e.target.closest(".qcard");
  if (card) openDrawer(card.dataset.id);
});
$("cards").addEventListener("keydown", (e) => {
  const card = e.target.closest(".qcard");
  if (card && e.key === "Enter") openDrawer(card.dataset.id);
});

$("drawer").addEventListener("click", (e) => { if (e.target.hasAttribute("data-close")) closeDrawer(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

$("adv-location").addEventListener("change", fillServices);
$("adv-btn").addEventListener("click", runAdvisor);

/* ---------- start ---------- */
load();
setInterval(load, REFRESH_MS);
setInterval(tickClock, 1000);