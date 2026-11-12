const MODEL_COLORS = ["var(--sage)", "var(--caramel)", "#7f9cb0", "#b48aa8"];
const REFRESH_EVERY_MS = 30000;
const SVG_NS = "http://www.w3.org/2000/svg";

const $ = (id) => document.getElementById(id);

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = String(text);
  return div.innerHTML;
}

const seconds = (ms) => (ms == null ? "–" : `${(ms / 1000).toFixed(1)} s`);
const usd = (value) => (value > 0 && value < 0.01 ? `$${value.toFixed(5)}` : `$${(value || 0).toFixed(2)}`);
const number = (value) => (value || 0).toLocaleString("en-US");

function colorFor(model, models) {
  const i = models.indexOf(model);
  return i === -1 ? "var(--muted)" : MODEL_COLORS[i % MODEL_COLORS.length];
}

function renderTiles(stats) {
  const answered = stats.requests - stats.errors;
  const errorRate = stats.requests ? Math.round((stats.errors / stats.requests) * 100) : 0;
  const tiles = [
    ["Questions", number(stats.requests), `${number(stats.errors)} failed (${errorRate}%)`],
    ["Average time", seconds(stats.latency_ms.avg), `p95 ${seconds(stats.latency_ms.p95)}`],
    ["Tokens", number(stats.tokens.input + stats.tokens.output),
      `${number(stats.tokens.input)} in / ${number(stats.tokens.output)} out`],
    ["Estimated cost", usd(stats.estimated_cost_usd),
      answered ? `${usd(stats.estimated_cost_usd / answered)} per answer` : "no answers yet"],
  ];
  $("tiles").innerHTML = tiles.map(([label, value, detail]) => `
    <div class="tile glass">
      <span class="tile-label">${label}</span>
      <strong class="tile-value">${value}</strong>
      <span class="tile-detail">${detail}</span>
    </div>`).join("");
}

// A simple bar chart in SVG: one bar per call, optionally stacked
function barChart(container, calls, segments, formatMax) {
  const width = 600, height = 200, pad = { top: 12, right: 8, bottom: 8, left: 44 };
  const totals = calls.map((call) => segments.reduce((sum, s) => sum + s.value(call), 0));
  const max = Math.max(...totals, 1);
  const slot = (width - pad.left - pad.right) / Math.max(calls.length, 1);
  const barWidth = Math.max(2, Math.min(18, slot * 0.7));
  const y = (v) => pad.top + (height - pad.top - pad.bottom) * (1 - v / max);

  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("preserveAspectRatio", "none");

  for (const fraction of [0, 0.5, 1]) {
    const lineY = y(max * fraction);
    svg.insertAdjacentHTML("beforeend", `
      <line x1="${pad.left}" x2="${width - pad.right}" y1="${lineY}" y2="${lineY}" class="grid"/>
      <text x="${pad.left - 6}" y="${lineY + 4}" class="axis">${formatMax(max * fraction)}</text>`);
  }

  calls.forEach((call, i) => {
    const x = pad.left + slot * i + (slot - barWidth) / 2;
    let base = 0;
    for (const segment of segments) {
      const value = segment.value(call);
      if (!value) continue;
      const rect = document.createElementNS(SVG_NS, "rect");
      rect.setAttribute("x", x);
      rect.setAttribute("y", y(base + value));
      rect.setAttribute("width", barWidth);
      rect.setAttribute("height", Math.max(1, y(base) - y(base + value)));
      rect.setAttribute("rx", 2);
      rect.style.fill = segment.color(call);  // CSS variables work in style, not in the fill attribute
      const title = document.createElementNS(SVG_NS, "title");
      title.textContent = segment.title(call);
      rect.appendChild(title);
      svg.appendChild(rect);
      base += value;
    }
  });

  container.replaceChildren(svg);
}

function renderCharts(calls, models) {
  const answered = calls.filter((c) => c.status === "ok");
  barChart($("latency-chart"), calls, [{
    value: (c) => c.latency_ms,
    color: (c) => (c.status === "ok" ? colorFor(c.model, models) : "var(--error)"),
    title: (c) => `${c.status === "ok" ? c.model : "error"}: ${seconds(c.latency_ms)}`,
  }], (v) => `${(v / 1000).toFixed(0)}s`);

  barChart($("tokens-chart"), answered, [
    { value: (c) => c.input_tokens, color: () => "var(--caramel)", title: (c) => `${number(c.input_tokens)} input tokens` },
    { value: (c) => c.output_tokens, color: () => "var(--sage)", title: (c) => `${number(c.output_tokens)} output tokens` },
  ], (v) => (v >= 1000 ? `${(v / 1000).toFixed(1)}k` : Math.round(v)));

  const failed = calls.some((c) => c.status !== "ok");
  $("latency-legend").innerHTML = models.map((m) =>
    `<span><i class="swatch" style="background: ${colorFor(m, models)}"></i>${escapeHtml(m)}</span>`).join("")
    + (failed ? `<span><i class="swatch" style="background: var(--error)"></i>error</span>` : "");
}

function renderModels(stats, models) {
  const answered = stats.requests - stats.errors;
  $("models").innerHTML = models.map((name) => {
    const m = stats.by_model[name];
    const share = answered ? Math.round((m.requests / answered) * 100) : 0;
    return `<tr>
      <td><i class="swatch" style="background: ${colorFor(name, models)}"></i>${escapeHtml(name)}</td>
      <td>${number(m.requests)}</td>
      <td><div class="share"><div class="score-bar"><span style="width: ${share}%"></span></div>${share}%</div></td>
      <td>${seconds(m.avg_latency_ms)}</td>
      <td>${number(m.input_tokens)} / ${number(m.output_tokens)}</td>
      <td>${usd(m.estimated_cost_usd)}</td>
    </tr>`;
  }).join("");
}

function renderCalls(calls) {
  $("calls").innerHTML = [...calls].reverse().slice(0, 15).map((c) => `<tr>
    <td>${new Date(c.time).toLocaleString("en-GB", { dateStyle: "short", timeStyle: "short" })}</td>
    <td><span class="status ${c.status === "ok" ? "ok" : "bad"}">${c.status === "ok" ? "ok" : escapeHtml(c.error || "error")}</span></td>
    <td>${escapeHtml(c.model || "–")}</td>
    <td>${c.attempts ?? "–"}</td>
    <td>${seconds(c.latency_ms)}</td>
    <td>${c.status === "ok" ? `${number(c.input_tokens)} / ${number(c.output_tokens)}` : "–"}</td>
    <td>${c.status === "ok" ? usd(c.estimated_cost_usd) : "–"}</td>
  </tr>`).join("");
}

async function load() {
  const button = $("refresh");
  button.disabled = true;
  try {
    const [stats, calls] = await Promise.all([
      fetch("/stats").then((r) => r.json()),
      fetch("/stats/recent?limit=40").then((r) => r.json()),
    ]);
    // models sorted by how many answers they gave, so the main model usually gets the first colour
    const models = Object.keys(stats.by_model).sort((a, b) => stats.by_model[b].requests - stats.by_model[a].requests);

    $("empty").hidden = stats.requests > 0;
    renderTiles(stats);
    renderCharts(calls, models);
    renderModels(stats, models);
    renderCalls(calls);
    $("note").textContent = stats.note;
    $("updated").textContent = `Updated ${new Date().toLocaleTimeString("en-GB", { timeStyle: "short" })}`;
  } catch (_) {
    $("updated").textContent = "Couldn't load the stats.";
  } finally {
    button.disabled = false;
  }
}

$("refresh").addEventListener("click", load);
load();
setInterval(() => { if (!document.hidden) load(); }, REFRESH_EVERY_MS);
