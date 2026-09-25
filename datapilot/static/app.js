// DataPilot chat. Everything from the server (answers, data, names) is untrusted:
// it is inserted with textContent, never innerHTML.

const $ = (selector) => document.querySelector(selector);
const state = { conversationId: null, name: "", gemini: null, health: null, setupReturn: "welcome" };
const NAME_KEY = "datapilot.name";
const LOOK_KEY = "datapilot.look";
const MODE_KEY = "datapilot.thorough";
// The designs. `history` names the question list in the sidebar.
const LOOKS = {
  workspace: { label: "Workspace", history: "Recent questions" },
  deck: { label: "Flight deck", history: "Flight log" },
};
const DEFAULT_LOOK = "workspace";
const SVG_NS = "http://www.w3.org/2000/svg";
const TABLE_PREVIEW_ROWS = 50;

// ---------- small helpers ----------

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else node.setAttribute(key, value);
  }
  for (const child of children) if (child) node.append(child);
  return node;
}

function svg(tag, attrs = {}) {
  const node = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}

// A small, fixed icon set (outline, 24px grid). Built from constant shapes only.
const ICONS = {
  check: [["path", { d: "M5 12l5 5L20 7" }]],
  plus: [["path", { d: "M12 5v14M5 12h14" }]],
  send: [["path", { d: "M12 19V5M5 12l7-7 7 7" }]],
  copy: [["rect", { x: 8, y: 8, width: 12, height: 12, rx: 2 }], ["path", { d: "M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" }]],
  download: [["path", { d: "M12 4v12M7 11l5 5 5-5M5 20h14" }]],
  database: [["ellipse", { cx: 12, cy: 6, rx: 8, ry: 3 }], ["path", { d: "M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" }]],
  shield: [["path", { d: "M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" }], ["path", { d: "M9 12l2 2 4-4" }]],
  code: [["path", { d: "M8 8l-4 4 4 4M16 8l4 4-4 4" }]],
  table: [["rect", { x: 3, y: 4, width: 18, height: 16, rx: 2 }], ["path", { d: "M3 10h18M9 10v10" }]],
  list: [["path", { d: "M9 6h11M9 12h11M9 18h11M4 6h.01M4 12h.01M4 18h.01" }]],
  alert: [["path", { d: "M12 9v4M12 17h.01" }], ["path", { d: "M10.3 3.9L2.4 17.5A2 2 0 0 0 4.1 20.5h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" }]],
  bolt: [["path", { d: "M13 3L4 14h7l-1 7 9-11h-7z" }]],
};

function icon(name) {
  const root = svg("svg", { class: "icon", viewBox: "0 0 24 24", "aria-hidden": "true" });
  for (const [tag, attrs] of ICONS[name] || []) root.append(svg(tag, attrs));
  return root;
}

function fillIcons(scope = document) {
  for (const holder of scope.querySelectorAll("[data-icon]")) {
    if (!holder.firstChild || holder.firstChild.nodeName !== "svg") holder.prepend(icon(holder.dataset.icon));
  }
}

function store(key, value) {
  try { localStorage.setItem(key, value); } catch { /* storage may be blocked */ }
}
function load(key) {
  try { return localStorage.getItem(key) || ""; } catch { return ""; }
}
const remember = (name) => store(NAME_KEY, name);
const recall = () => load(NAME_KEY);

async function post(url, body) {
  return handle(await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }));
}

async function getJson(url) {
  return handle(await fetch(url));
}

async function handle(response) {
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    const message = typeof detail === "string" ? detail
      : Array.isArray(detail) ? detail.map((d) => d.msg).join("; ")
      : detail && detail.message ? detail.message : "";
    const error = new Error(message || `Request failed (HTTP ${response.status}).`);
    error.status = response.status;
    error.code = detail && detail.code;
    throw error;
  }
  return data;
}

// Years, months and ids are labels, not quantities: never "2,026". The id match is
// case-sensitive so "StudentId" is an id but "TotalPaid" is not.
const TIME_COLUMN = /year|month|quarter|week|day|date/i;
const ID_COLUMN = /(^|_)(id|ID)$|Id$/;
const isLabelColumn = (column) => TIME_COLUMN.test(column) || ID_COLUMN.test(column);
const isNumber = (value) => value !== null && value !== "" && typeof value !== "boolean" && !isNaN(Number(value));
function formatNumber(value) {
  const n = Number(value);
  return Number.isInteger(n) ? n.toLocaleString() : n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
const formatCell = (column, value) =>
  value === null || value === undefined ? "" : isNumber(value) && !isLabelColumn(column) ? formatNumber(value) : String(value);
// "StudentCount" -> "Student count", "avg_pct" -> "Avg pct"
function humanize(column) {
  const words = String(column || "Value").replace(/_/g, " ").replace(/([a-z0-9])([A-Z])/g, "$1 $2").trim().toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
}
// Gemini sometimes adds markdown emphasis; show plain text.
const plain = (text) => String(text ?? "").replace(/\*\*(.+?)\*\*/g, "$1").replace(/^\s*\*\s+/gm, "- ");
const plural = (n, word) => `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;

function toast(text) {
  const box = $("#toast");
  box.textContent = text;
  box.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { box.hidden = true; }, 2200);
}

// ---------- design switcher ----------

const lookSelects = () => [$("#look-front"), $("#look-chat")];

function applyLook(look) {
  if (!LOOKS[look]) look = DEFAULT_LOOK;   // e.g. a design that was removed
  document.documentElement.dataset.look = look;
  store(LOOK_KEY, look);
  for (const select of lookSelects()) select.value = look;
  $("#history-title").textContent = LOOKS[look].history;
}

function initLooks() {
  for (const select of lookSelects()) {
    for (const [value, look] of Object.entries(LOOKS)) select.append(el("option", { value, text: look.label }));
    select.addEventListener("change", () => applyLook(select.value));
  }
  applyLook(document.documentElement.dataset.look || load(LOOK_KEY));
}

// ---------- answer mode ----------

const thorough = () => $("#thorough").checked;

function updateModeNote() {
  $("#mode-note").textContent = thorough()
    ? "Investigates in several steps: 2-4 Gemini calls per question."
    : "Fast: usually 1 Gemini call per question. Repeated questions are free.";
  store(MODE_KEY, thorough() ? "1" : "");
}

// ---------- thread ----------

const thread = () => $("#thread");

function scrollToEnd() {
  const wrap = $(".thread-wrap");
  wrap.scrollTop = wrap.scrollHeight;
}

function cardHead(extra = []) {
  const who = el("span", { class: "who" }, el("span", { class: "logo-mark", "aria-hidden": "true" }), document.createTextNode("DataPilot"));
  return el("div", { class: "card-head" }, who, el("span", { class: "spacer" }), ...extra);
}

function addUserMessage(text) {
  const item = el("li", { class: "message user" }, el("div", { class: "bubble", text }));
  thread().append(item);
  scrollToEnd();
  return item;
}

// Sidebar question history: each entry scrolls back to where it was asked.
function addToHistory(question, messageItem) {
  const list = $("#history");
  list.querySelector(".side-empty")?.remove();
  const button = el("button", { type: "button", text: question, title: question });
  button.addEventListener("click", () => messageItem.scrollIntoView({ behavior: "smooth", block: "start" }));
  list.append(el("li", {}, button));
}

function resetHistory() {
  $("#history").replaceChildren(el("li", { class: "side-empty", text: "Questions you ask appear here." }));
}

function addWorking() {
  const dots = el("span", { class: "dots", "aria-hidden": "true" }, el("span"), el("span"), el("span"));
  const label = thorough() ? "Investigating your question..." : "Analyzing your question...";
  const item = el("li", { class: "message assistant" },
    el("div", { class: "card" }, el("div", { class: "working" }, dots, el("span", { text: label }))));
  thread().append(item);
  scrollToEnd();
  return item;
}

function addError(text, action = null) {
  const card = el("div", { class: "card error" }, cardHead(), el("p", { class: "answer-text", text }));
  if (action) {
    const button = el("button", { class: "button quiet", type: "button", text: action.label });
    button.addEventListener("click", action.run);
    card.append(el("div", {}, button));
  }
  thread().append(el("li", { class: "message assistant" }, card));
  scrollToEnd();
}

function suggestionButton(question, className) {
  const button = el("button", { class: className, type: "button", text: question });
  button.addEventListener("click", () => ask(question));
  return button;
}

function addWelcome(data) {
  const summary = el("dl", { class: "summary-grid", "aria-label": "What's in the database" },
    ...data.counts.map((c) => el("div", {}, el("dt", { text: c.label }), el("dd", { text: formatNumber(c.rows) }))));
  const chips = el("div", { class: "suggestions" }, ...data.suggestions.map((q) => suggestionButton(q, "chip")));
  const card = el("div", { class: "card" }, cardHead(), el("p", { class: "answer-text", text: plain(data.greeting) }), summary, chips);
  thread().append(el("li", { class: "message assistant" }, card));

  // The same summary and suggestions feed the sidebar.
  $("#side-counts").replaceChildren(...data.counts.map((c) =>
    el("div", {}, el("dt", { text: c.label }), el("dd", { text: formatNumber(c.rows) }))));
  $("#side-suggestions").replaceChildren(...data.suggestions.map((q) => suggestionButton(q, "")));
  resetHistory();
  scrollToEnd();
}

// A one-row, one-number result reads best as a big figure.
function kpiFor(data) {
  if (data.rows.length !== 1 || data.columns.length !== 1) return null;
  const column = data.columns[0];
  const value = data.rows[0][column];
  if (!isNumber(value) || isLabelColumn(column)) return null;
  return el("div", { class: "kpi" },
    el("span", { class: "value", text: formatNumber(value) }),
    el("span", { class: "label", text: column ? humanize(column) : "Result" }));
}

function addAnswer(data) {
  const head = [el("span", { class: `badge${data.mode === "thorough" ? " accent" : ""}`, text: data.mode === "thorough" ? "Thorough" : "Fast" }),
    el("span", { text: `${(data.duration_ms / 1000).toFixed(1)} s` })];
  const card = el("div", { class: "card" }, cardHead(head));

  const kpi = data.sql ? kpiFor(data) : null;
  if (kpi) card.append(kpi);
  card.append(el("p", { class: "answer-text", text: plain(data.answer) }));
  if (data.chart && data.chart.type !== "none") card.append(renderChart(data.chart));
  if (data.sql || data.steps.length) card.append(renderTabs(data));
  card.append(renderFoot(data));

  thread().append(el("li", { class: "message assistant" }, card));
  scrollToEnd();
}

function renderFoot(data) {
  const foot = el("div", { class: "card-foot" });
  if (data.sql) {
    const verified = data.grounded
      ? el("span", { class: "verified" }, icon("check"), document.createTextNode("Verified against the data"))
      : el("span", { class: "verified warn" }, icon("alert"), document.createTextNode(`Couldn't verify ${data.ungrounded_numbers.join(", ")}`));
    foot.append(verified, el("span", { text: `${plural(data.row_count, "row")}${data.truncated ? " (limited)" : ""}` }));
  }
  foot.append(el("span", { text: data.cached ? "Cached, 0 Gemini calls" : plural(data.llm_calls, "Gemini call") }));
  foot.append(el("span", { class: "spacer" }));
  if (data.sql) {
    const copy = el("button", { class: "icon-button", type: "button" }, icon("copy"), document.createTextNode("Copy SQL"));
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(data.sql.trim()); toast("SQL copied"); }
      catch { toast("Couldn't copy. Select the SQL and copy it instead."); }
    });
    foot.append(copy);
  }
  if (data.rows.length) {
    const download = el("button", { class: "icon-button", type: "button" }, icon("download"), document.createTextNode("CSV"));
    download.addEventListener("click", () => downloadCsv(data));
    foot.append(download);
  }
  return foot;
}

// Table / SQL / Steps tabs. Nothing is shown until a tab is chosen, to keep answers short.
function renderTabs(data) {
  const panels = [];
  if (data.rows.length) panels.push(["table", "Table", () => renderTable(data)]);
  if (data.sql) panels.push(["code", "SQL", () => el("pre", { class: "sql", text: data.sql.trim() })]);
  if (data.steps.length) panels.push(["list", "Steps", () => renderSteps(data.steps)]);

  const wrap = el("div", { class: "tab-wrap" });
  const bar = el("div", { class: "tabs", role: "tablist" });
  const panel = el("div", { class: "tab-panel", role: "tabpanel", hidden: "" });
  const buttons = panels.map(([iconName, label, build]) => {
    const button = el("button", { class: "tab", type: "button", role: "tab", "aria-selected": "false" }, icon(iconName), document.createTextNode(label));
    button.addEventListener("click", () => {
      const open = button.getAttribute("aria-selected") === "true";
      for (const b of buttons) b.setAttribute("aria-selected", "false");
      if (open) { panel.hidden = true; return; }
      button.setAttribute("aria-selected", "true");
      panel.replaceChildren(build());
      panel.hidden = false;
    });
    return button;
  });
  bar.append(...buttons);
  wrap.append(bar, panel);
  return wrap;
}

function renderTable(data) {
  const numeric = new Set(data.columns.filter((c) => data.rows.every((row) => row[c] === null || isNumber(row[c]))));
  const head = el("tr", {}, ...data.columns.map((c) => el("th", { class: numeric.has(c) ? "num" : "", text: c || "(value)" })));
  const rows = data.rows.slice(0, TABLE_PREVIEW_ROWS).map((row) => el("tr", {},
    ...data.columns.map((c) => el("td", { class: numeric.has(c) ? "num" : "", text: formatCell(c, row[c]) }))));
  const box = el("div", {}, el("div", { class: "table-wrap" },
    el("table", { class: "data" }, el("thead", {}, head), el("tbody", {}, ...rows))));
  if (data.rows.length > TABLE_PREVIEW_ROWS) {
    box.append(el("p", { class: "table-note", text: `Showing ${TABLE_PREVIEW_ROWS} of ${data.rows.length} rows. Download the CSV for all of them.` }));
  }
  return box;
}

function renderSteps(steps) {
  return el("ol", { class: "steps" }, ...steps.map((step) => {
    const li = el("li", { class: step.ok ? "" : "fail" },
      el("span", { class: "state" }, icon(step.ok ? "check" : "alert")),
      el("span", {}, el("code", { text: step.tool }), document.createTextNode(` - ${step.summary}`)),
      el("span", { class: "ms", text: `${Math.round(step.duration_ms)} ms` }));
    return li;
  }));
}

function downloadCsv(data) {
  const escape = (value) => {
    const text = value === null || value === undefined ? "" : String(value);
    return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  const lines = [data.columns.map(escape).join(","), ...data.rows.map((row) => data.columns.map((c) => escape(row[c])).join(","))];
  const url = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" }));
  const link = el("a", { href: url, download: "datapilot-result.csv" });
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

// ---------- charts (single series; spec chosen by server-side rules) ----------

function niceTicks(max, count = 5) {
  if (max <= 0) return [0, 1];
  const raw = max / count;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw);
  return Array.from({ length: Math.ceil(max / step) + 1 }, (_, i) => i * step);
}

const tooltip = () => $("#tooltip");
function showTip(target, x, y, crosshair) {
  const tip = tooltip();
  tip.replaceChildren(el("strong", { text: target.dataset.value }), el("span", { text: target.dataset.label }));
  tip.hidden = false;
  tip.style.left = `${Math.min(x + 14, window.innerWidth - 180)}px`;
  tip.style.top = `${y + 14}px`;
  if (crosshair && target.dataset.x) {
    crosshair.setAttribute("x1", target.dataset.x);
    crosshair.setAttribute("x2", target.dataset.x);
    crosshair.style.visibility = "visible";
  }
}
function hideTip(crosshair) {
  tooltip().hidden = true;
  if (crosshair) crosshair.style.visibility = "hidden";
}
function wireTooltip(mark, crosshair) {
  mark.setAttribute("tabindex", "0");
  mark.classList.add("mark");
  mark.addEventListener("pointermove", (e) => showTip(mark, e.clientX, e.clientY, crosshair));
  mark.addEventListener("pointerleave", () => hideTip(crosshair));
  mark.addEventListener("focus", () => { const r = mark.getBoundingClientRect(); showTip(mark, r.left, r.top, crosshair); });
  mark.addEventListener("blur", () => hideTip(crosshair));
}

function renderChart(spec) {
  const box = el("figure", { class: "chart" });
  box.append(spec.type === "line" ? lineChart(spec) : barChart(spec));
  box.append(el("figcaption", { class: "chart-caption", text: `${humanize(spec.y_label)} by ${humanize(spec.x_label).toLowerCase()}` }));
  return box;
}

// Draw at the card's real width so chart text stays at its CSS size on phones.
const chartWidth = () => Math.max(280, Math.min(760, (thread().clientWidth || 760) - 42));

function barChart(spec) {
  const width = chartWidth(), labelWidth = Math.min(170, Math.round(width * 0.36)), valueRoom = 56;
  const band = 28, bar = 18;
  const ticks = niceTicks(Math.max(...spec.points.map((p) => p.value)));
  const top = ticks[ticks.length - 1];
  const plot = width - labelWidth - valueRoom;
  const height = band * spec.points.length + 28;
  const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": `${spec.y_label} by ${spec.x_label}` });

  for (const tick of ticks) {
    const x = labelWidth + (plot * tick) / top;
    root.append(svg("line", { class: "grid", x1: x, y1: 0, x2: x, y2: height - 22 }));
    const t = svg("text", { class: "tick", x, y: height - 6, "text-anchor": "middle" });
    t.textContent = formatNumber(tick);
    root.append(t);
  }
  spec.points.forEach((point, i) => {
    const y = i * band + (band - bar) / 2;
    const length = Math.max((plot * point.value) / top, 0);
    const r = Math.min(4, length);
    const g = svg("g", { "data-label": point.label, "data-value": formatNumber(point.value) });
    g.append(svg("rect", { class: "hit", x: 0, y: i * band, width, height: band }));
    // Rounded at the data end, square at the baseline.
    g.append(svg("path", {
      class: "bar",
      d: `M${labelWidth},${y} h${length - r} a${r},${r} 0 0 1 ${r},${r} v${bar - 2 * r} a${r},${r} 0 0 1 ${-r},${r} h${-(length - r)} z`,
    }));
    const label = svg("text", { class: "label", x: labelWidth - 8, y: y + bar / 2 + 4, "text-anchor": "end" });
    const maxChars = Math.floor(labelWidth / 7);
    label.textContent = point.label.length > maxChars ? `${point.label.slice(0, maxChars - 1)}...` : point.label;
    const value = svg("text", { class: "value", x: labelWidth + length + 6, y: y + bar / 2 + 4 });
    value.textContent = formatNumber(point.value);
    g.append(label, value);
    wireTooltip(g);
    root.append(g);
  });
  return root;
}

function lineChart(spec) {
  const width = chartWidth(), height = 260, left = 52, right = 24, topPad = 14, bottom = 40;
  const ticks = niceTicks(Math.max(...spec.points.map((p) => p.value)));
  const top = ticks[ticks.length - 1];
  const plotW = width - left - right, plotH = height - topPad - bottom;
  const n = spec.points.length;
  const xOf = (i) => left + (n > 1 ? (plotW * i) / (n - 1) : plotW / 2);
  const yOf = (v) => topPad + plotH * (1 - v / top);
  const root = svg("svg", { viewBox: `0 0 ${width} ${height}`, role: "img", "aria-label": `${spec.y_label} by ${spec.x_label}` });

  for (const tick of ticks) {
    root.append(svg("line", { class: "grid", x1: left, y1: yOf(tick), x2: width - right, y2: yOf(tick) }));
    const t = svg("text", { class: "tick", x: left - 8, y: yOf(tick) + 4, "text-anchor": "end" });
    t.textContent = formatNumber(tick);
    root.append(t);
  }
  const every = Math.max(1, Math.ceil(n / Math.max(2, Math.floor(plotW / 70))));
  spec.points.forEach((p, i) => {
    if (i % every && i !== n - 1) return;
    const t = svg("text", { class: "tick", x: xOf(i), y: height - bottom + 20, "text-anchor": "middle" });
    t.textContent = p.label;
    root.append(t);
  });
  root.append(svg("polyline", { class: "line", points: spec.points.map((p, i) => `${xOf(i)},${yOf(p.value)}`).join(" ") }));
  const last = spec.points[n - 1];
  const end = svg("text", { class: "value", x: xOf(n - 1), y: yOf(last.value) - 10, "text-anchor": "end" });
  end.textContent = formatNumber(last.value);
  root.append(end);

  const crosshair = svg("line", { class: "crosshair", x1: 0, y1: topPad, x2: 0, y2: height - bottom });
  root.append(crosshair);
  spec.points.forEach((p, i) => root.append(svg("circle", { class: "dot", cx: xOf(i), cy: yOf(p.value), r: 4 })));
  const bandW = plotW / Math.max(n - 1, 1);
  spec.points.forEach((p, i) => {
    const hit = svg("rect", {
      class: "hit", x: xOf(i) - bandW / 2, y: topPad, width: bandW, height: plotH,
      "data-x": xOf(i), "data-label": p.label, "data-value": formatNumber(p.value),
    });
    wireTooltip(hit, crosshair);
    root.append(hit);
  });
  return root;
}

// ---------- status ----------

async function refreshStatus() {
  try { state.gemini = await getJson("/setup/status"); } catch { state.gemini = null; }
  try { state.health = await getJson("/health"); } catch { state.health = null; }
  return state.gemini;
}

function pill(target, text, ok, iconName) {
  target.replaceChildren(el("span", { class: "dot", "aria-hidden": "true" }), icon(iconName), document.createTextNode(text));
  target.classList.toggle("off", !ok);
}

function renderStatus() {
  const health = state.health, gemini = state.gemini;
  if (health) {
    pill($("#db-pill"), `${health.database} (${plural(health.tables, "table")})`, true, "database");
    $("#entry-status").textContent = `Connected to ${health.database} (${plural(health.tables, "table")}).`;
  } else {
    pill($("#db-pill"), "Database unavailable", false, "database");
    $("#entry-status").textContent = "";
  }
  const connected = gemini && gemini.gemini_configured;
  pill($("#model-pill"), connected ? gemini.model : "Gemini not connected", !!connected, "bolt");
  $("#gemini-line").textContent = connected
    ? `Gemini connected: ${gemini.model}${gemini.key_hint ? ` (key ${gemini.key_hint})` : ""}`
    : "Gemini is not connected.";
}

// ---------- flow ----------

function showView(id) {
  for (const view of ["setup", "welcome", "chat"]) $(`#${view}`).hidden = view !== id;
  $("#look-bar").hidden = id === "chat";   // the chat has its own switcher in the top bar
}

function showWelcome() {
  renderStatus();
  showView("welcome");
  $("#name").value = state.name || recall();
  $("#name").focus();
}

// returnTo: where to go after connecting ("welcome" or "chat").
function showSetup(returnTo = "welcome") {
  state.setupReturn = returnTo;
  const status = state.gemini;
  $("#model").value = (status && status.model) || "gemini-2.5-flash-lite";
  $("#api-key").value = "";
  $("#setup-error").hidden = true;
  $("#setup-back").hidden = !(status && status.gemini_configured) && returnTo !== "chat";
  showView("setup");
  $("#api-key").focus();
}

async function start(event) {
  event.preventDefault();
  const name = $("#name").value.trim();
  const error = $("#welcome-error");
  if (!name) {
    error.textContent = "Enter your name to start.";
    error.hidden = false;
    $("#name").focus();
    return;
  }
  error.hidden = true;
  const button = $("#start");
  button.disabled = true;
  button.textContent = "Starting...";
  try {
    const data = await post("/welcome", { name });
    state.conversationId = data.conversation_id;
    state.name = data.name;
    remember(data.name);
    const initials = data.name.split(" ").filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
    $("#avatar").textContent = initials || "?";
    $("#avatar").setAttribute("aria-label", `Signed in as ${data.name}`);
    $("#avatar").title = `Signed in as ${data.name}`;
    renderStatus();
    showView("chat");
    thread().replaceChildren();
    addWelcome(data);
    $("#question").focus();
  } catch (e) {
    error.textContent = e.status ? e.message : "Couldn't reach DataPilot. Check that the server is running, then try again.";
    error.hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Start chatting";
  }
}

let busy = false;
async function ask(question) {
  question = question.trim();
  if (!question || busy) return;
  busy = true;
  $("#send").disabled = true;
  $("#question").value = "";
  autosize();
  addToHistory(question, addUserMessage(question));
  const working = addWorking();
  try {
    const data = await post(`/conversations/${state.conversationId}/ask`,
      { question, mode: thorough() ? "thorough" : "fast" });
    working.remove();
    addAnswer(data);
  } catch (e) {
    working.remove();
    if (e.code === "gemini_not_configured") {
      addError("Gemini isn't connected yet, so DataPilot can't read questions.",
        { label: "Connect Gemini", run: () => showSetup("chat") });
    } else if (e.status === 404) {
      addError("This chat has expired because the server restarted.", { label: "Start a new chat", run: startNewChat });
    } else if (e.status) addError(e.message);
    else addError("Couldn't reach DataPilot. Check that the server is running, then try again.");
  } finally {
    busy = false;
    $("#send").disabled = false;
    $("#question").focus();
  }
}

function startNewChat() {
  if (state.conversationId) {
    fetch(`/conversations/${state.conversationId}`, { method: "DELETE" }).catch(() => {});
  }
  state.conversationId = null;
  showWelcome();
}

async function connect(event) {
  event.preventDefault();
  const apiKey = $("#api-key").value.trim();
  const model = $("#model").value.trim();
  const error = $("#setup-error");
  if (!apiKey || !model) {
    error.textContent = !apiKey ? "Paste your Gemini API key." : "Enter a model name.";
    error.hidden = false;
    return;
  }
  const button = $("#connect");
  button.disabled = true;
  button.textContent = "Checking the key...";
  try {
    state.gemini = await post("/setup/gemini", { api_key: apiKey, model, save_to_env_file: $("#save-env").checked });
    $("#api-key").value = "";   // don't keep the key in the page
    renderStatus();
    if (state.setupReturn === "chat" && state.conversationId) {
      showView("chat");
      addError("Gemini is connected. Ask your question again.");
    } else {
      showWelcome();
    }
  } catch (e) {
    error.textContent = e.status ? e.message : "Couldn't reach DataPilot. Check that the server is running, then try again.";
    error.hidden = false;
  } finally {
    button.disabled = false;
    button.textContent = "Connect Gemini";
  }
}

function leaveSetup() {
  if (state.setupReturn === "chat" && state.conversationId) showView("chat");
  else showWelcome();
}

function autosize() {
  const box = $("#question");
  box.style.height = "auto";
  box.style.height = `${Math.min(box.scrollHeight, 180)}px`;
}

async function boot() {
  const status = await refreshStatus();
  renderStatus();
  if (status && !status.gemini_configured) showSetup("welcome");
  else showWelcome();
}

$("#welcome-form").addEventListener("submit", start);
$("#composer").addEventListener("submit", (e) => { e.preventDefault(); ask($("#question").value); });
$("#question").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask($("#question").value); }
});
$("#question").addEventListener("input", autosize);
$("#new-chat").addEventListener("click", startNewChat);
$("#setup-form").addEventListener("submit", connect);
$("#setup-back").addEventListener("click", leaveSetup);
$("#change-key").addEventListener("click", () => showSetup("welcome"));
$("#thorough").checked = load(MODE_KEY) === "1";
$("#thorough").addEventListener("change", updateModeNote);
fillIcons();
initLooks();
updateModeNote();
boot();
