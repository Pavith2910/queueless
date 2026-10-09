// staff.js - renders the staff cards and sends actions to the staff API.
const grid = document.getElementById("staff-grid");
const logList = document.getElementById("log-list");
const toast = document.getElementById("toast");

function cardHTML(q) {
  return `
  <article class="staff-card" data-id="${q.location_id}" data-counters="${q.counters}">
    <header>
      <div>
        <h3>${q.name}</h3>
        <small>${q.category} · ${q.opening_hours.open}–${q.opening_hours.close}</small>
      </div>
      <span class="pill pill-${q.status}">${q.status}</span>
    </header>

    <div class="staff-numbers">
      <div><span class="big">${q.waiting}</span><small>waiting</small></div>
      <div><span class="big">${q.is_open ? q.est_wait_min : "–"}</span><small>min est.</small></div>
      <div><span class="big">${q.avg_service_seconds}</span><small>sec / person</small></div>
    </div>

    <div class="staff-actions">
      <button data-action="join" data-count="1">+1 joined</button>
      <button data-action="join" data-count="5">+5</button>
      <button data-action="serve" class="primary">Served ✓</button>
    </div>

    <div class="staff-row">
      <label>Counters open</label>
      <div class="stepper">
        <button data-action="counters" data-delta="-1">−</button>
        <span>${q.counters}</span>
        <button data-action="counters" data-delta="1">+</button>
      </div>
    </div>

    <form class="staff-row set-form">
      <label>Set exact count</label>
      <input type="number" min="0" max="500" placeholder="${q.waiting}" required>
      <button type="submit">Set</button>
    </form>
  </article>`;
}

async function loadAll() {
  // don't redraw while the user is typing in a box
  if (grid.contains(document.activeElement) && document.activeElement.tagName === "INPUT") return;
  const res = await fetch("/api/queues");
  const data = await res.json();
  grid.innerHTML = data.queues.map(cardHTML).join("");
}

async function post(id, action, body) {
  const res = await fetch(`/api/staff/queues/${id}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.status === 401) { window.location.href = "/staff/login"; return null; }
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Request failed");
  return data;
}

function describe(action, body) {
  if (action === "join") return `+${body.count} joined`;
  if (action === "serve") return "served 1";
  if (action === "set") return `count set to ${body.waiting}`;
  return `counters set to ${body.counters}`;
}

function addLog(text) {
  if (logList.querySelector(".muted")) logList.innerHTML = "";
  const time = new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  logList.insertAdjacentHTML("afterbegin", `<li><span>${time}</span> ${text}</li>`);
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2500);
}

async function run(card, action, body) {
  card.classList.add("busy");
  try {
    const q = await post(card.dataset.id, action, body);
    if (!q) return;
    card.outerHTML = cardHTML(q);
    const wait = q.is_open ? `${q.est_wait_min} min` : "closed";
    addLog(`<strong>${q.name}</strong>: ${describe(action, body)} → ${q.waiting} waiting, ${wait}`);
  } catch (err) {
    showToast(err.message);
    card.classList.remove("busy");
  }
}

grid.addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-action]");
  if (!btn) return;
  const card = btn.closest(".staff-card");
  const action = btn.dataset.action;
  let body = {};
  if (action === "join") body = { count: Number(btn.dataset.count) };
  if (action === "counters") {
    body = { counters: Math.max(0, Number(card.dataset.counters) + Number(btn.dataset.delta)) };
  }
  run(card, action, body);
});

grid.addEventListener("submit", (e) => {
  e.preventDefault();
  const card = e.target.closest(".staff-card");
  const input = e.target.querySelector("input");
  run(card, "set", { waiting: Number(input.value) });
});

loadAll();
setInterval(loadAll, 15000);   // refresh every 15 seconds