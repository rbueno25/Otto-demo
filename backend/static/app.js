const chat = document.getElementById("chat");
const empty = document.getElementById("empty");
const form = document.getElementById("form");
const input = document.getElementById("input");
const send = document.getElementById("send");
const health = document.getElementById("health");
const btnNew = document.getElementById("btnNew");

let history = [];
let busy = false;
let chartId = 0;

marked.use({ breaks: true, gfm: true });

function autoResize() {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 140) + "px";
  send.disabled = !input.value.trim() || busy;
}

input.addEventListener("input", autoResize);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

btnNew.addEventListener("click", () => {
  history = [];
  chat.innerHTML = "";
  empty.style.display = "";
  input.focus();
});

function scrollBottom() {
  requestAnimationFrame(() => { window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" }); });
}

function renderMarkdown(text) {
  return DOMPurify.sanitize(marked.parse(text));
}

function addUserMsg(text) {
  empty.style.display = "none";
  const row = document.createElement("div");
  row.className = "row user";
  row.innerHTML = `
    <div class="wrap">
      <div class="bubble"><p></p></div>
      <div class="user-avatar"><span class="ms">person</span></div>
    </div>`;
  row.querySelector("p").textContent = text;
  chat.appendChild(row);
  scrollBottom();
}

function addBotMsg() {
  empty.style.display = "none";
  const row = document.createElement("div");
  row.className = "row bot";
  row.innerHTML = `
    <div class="wrap">
      <div class="ai-avatar"><span class="ms">bolt</span></div>
      <div class="content">
        <div class="bubble"><div class="md"></div></div>
        <div class="think"><span></span><span></span><span></span></div>
        <div class="toolbar"></div>
        <div class="meta">
          <span class="ms">schedule</span><span class="timestamp"></span>
          <button class="copy-btn" title="Copiar"><span class="ms">content_copy</span></button>
        </div>
      </div>
    </div>`;
  const content = row.querySelector(".content");
  const md = row.querySelector(".md");
  const think = row.querySelector(".think");
  const toolbar = row.querySelector(".toolbar");
  const timestamp = row.querySelector(".timestamp");
  const copyBtn = row.querySelector(".copy-btn");
  const t0 = performance.now();
  chat.appendChild(row);
  scrollBottom();
  return { row, md, think, toolbar, timestamp, copyBtn, t0, content };
}

function startReply(m) {
  m.think.remove();
  m.copyBtn.addEventListener("click", () => {
    navigator.clipboard.writeText(m.md.textContent).catch(() => {});
  });
}

const PALETTE = ["#00488d", "#16a34a", "#f59e0b", "#dc2626", "#8b5cf6", "#0891b2", "#db2777", "#65a30d"];

function hexToRgba(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

function renderChart(spec) {
  const card = document.createElement("div");
  card.className = "chart-card";
  if (spec.titulo) {
    const t = document.createElement("div");
    t.className = "chart-title";
    t.textContent = spec.titulo;
    card.appendChild(t);
  }
  const wrap = document.createElement("div");
  wrap.className = "chart-wrap";
  const canvas = document.createElement("canvas");
  wrap.appendChild(canvas);
  card.appendChild(wrap);
  chat.appendChild(card);
  scrollBottom();

  const id = "otto-chart-" + chartId++;
  canvas.id = id;
  const labels = spec.etiquetas || [];
  const series = spec.series || [];
  const colors = series.map((_, i) => PALETTE[i % PALETTE.length]);
  const type = spec.tipo || "bar";

  let config;
  if (type === "pie" || type === "doughnut" || type === "polarArea") {
    const data = series[0] ? series[0].datos : [];
    config = {
      type,
      data: { labels, datasets: [{ data, backgroundColor: PALETTE.slice(0, labels.length), borderColor: "#fff", borderWidth: 2 }] },
      options: { responsive: true, maintainAspectRatio: true, plugins: { legend: { position: "right" } } },
    };
  } else if (type === "radar") {
    config = {
      type: "radar",
      data: { labels, datasets: series.map((s, i) => ({ label: s.nombre, data: s.datos, borderColor: colors[i], backgroundColor: hexToRgba(colors[i], 0.2), borderWidth: 2, pointBackgroundColor: colors[i] })) },
      options: { responsive: true, maintainAspectRatio: true },
    };
  } else {
    config = {
      type,
      data: { labels, datasets: series.map((s, i) => ({ label: s.nombre, data: s.datos, backgroundColor: hexToRgba(colors[i], 0.75), borderColor: colors[i], borderWidth: 2, tension: 0.3, fill: type === "line" })) },
      options: {
        responsive: true,
        maintainAspectRatio: true,
        plugins: { legend: { position: "top" } },
        scales: type === "line" || type === "bar" ? { y: { beginAtZero: true }, x: {} } : {},
      },
    };
  }

  requestAnimationFrame(() => new Chart(document.getElementById(id), config));
  scrollBottom();
}

function activeChip(msg, name) {
  const chips = msg.toolbar.querySelectorAll(".chip");
  for (const c of chips) if (c.dataset.name === name) return c;
  const chip = document.createElement("span");
  chip.className = "chip";
  chip.dataset.name = name;
  chip.textContent = "· " + name.replace(/_/g, " ");
  msg.toolbar.appendChild(chip);
  scrollBottom();
  return chip;
}

async function sendMessage(text) {
  busy = true;
  autoResize();
  addUserMsg(text);
  history.push({ role: "user", content: text });
  const msg = addBotMsg();
  let full = "";
  let started = false;

  const markStarted = () => {
    if (!started) { started = true; startReply(msg); }
  };

  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: history }),
    });

    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      throw new Error(err.detail || "Error del servidor");
    }
    if (!resp.body) throw new Error("Sin respuesta del servidor");

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        if (!raw.startsWith("data: ")) continue;
        let ev;
        try { ev = JSON.parse(raw.slice(6)); } catch { continue; }
        if (ev.type === "delta") {
          markStarted();
          full += ev.text;
          msg.md.innerHTML = renderMarkdown(full);
          scrollBottom();
        } else if (ev.type === "tool") {
          markStarted();
          const chip = activeChip(msg, ev.name);
          chip.classList.add("done");
          chip.textContent = "✓ " + ev.name.replace(/_/g, " ");
          scrollBottom();
        } else if (ev.type === "chart") {
          markStarted();
          renderChart(ev.spec);
        } else if (ev.type === "error") {
          markStarted();
          full = ev.message;
          msg.md.textContent = full;
          msg.row.classList.add("error");
          msg.content.querySelector(".bubble").classList.add("error");
        }
      }
    }
  } catch (err) {
    markStarted();
    full = "No se pudo obtener respuesta: " + err.message;
    msg.md.textContent = full;
    msg.content.querySelector(".bubble").classList.add("error");
  } finally {
    markStarted();
    if (full) history.push({ role: "assistant", content: full });
    msg.timestamp.textContent = ((performance.now() - msg.t0) / 1000).toFixed(1) + "s";
    busy = false;
    input.value = "";
    autoResize();
    input.focus();
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text || busy) return;
  sendMessage(text);
});

async function checkHealth() {
  try {
    const r = await fetch("/api/health");
    const d = await r.json();
    const okOdoo = d.odoo && d.odoo.ok === true;
    const okIa = d.ia && d.ia.configurado;
    const ok = okOdoo && okIa;
    health.classList.toggle("health-fail", !ok);
    const text = health.querySelector(".conn-text");
    if (ok) text.textContent = "Conectado a Odoo";
    else if (d.odoo && !d.odoo.ok) text.textContent = "Sin conexión a Odoo";
    else if (!okIa) text.textContent = "IA no configurada";
    else text.textContent = "Revisa configuración";
    if (d.odoo && !d.odoo.ok) health.title = JSON.stringify(d.odoo.detalle);
  } catch {
    health.classList.add("health-fail");
    health.querySelector(".conn-text").textContent = "Sin conexión";
  }
}

checkHealth();
setInterval(checkHealth, 30000);
