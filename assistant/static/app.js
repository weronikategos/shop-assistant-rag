const form = document.getElementById("ask-form");
const input = document.getElementById("question");
const thread = document.getElementById("thread");
const button = form.querySelector("button");

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// The model answers in plain text with a bit of Markdown (**bold**, "- " lists) and [n] citations.
function formatAnswer(text, messageId) {
  const blocks = [];
  let list = [];
  const inline = (line) =>
    escapeHtml(line)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\[(\d+)\]/g, `<button type="button" class="cite" data-target="${messageId}-src-$1">$1</button>`);

  for (const line of text.split("\n")) {
    const item = line.match(/^\s*[-*]\s+(.*)/);
    if (item) {
      list.push(`<li>${inline(item[1])}</li>`);
      continue;
    }
    if (list.length) {
      blocks.push(`<ul>${list.join("")}</ul>`);
      list = [];
    }
    if (line.trim()) blocks.push(`<p>${inline(line)}</p>`);
  }
  if (list.length) blocks.push(`<ul>${list.join("")}</ul>`);
  return blocks.join("");
}

function addMessage(role, html) {
  const msg = document.createElement("div");
  msg.className = `msg ${role}`;
  msg.innerHTML = `<div class="bubble">${html}</div>`;
  thread.appendChild(msg);
  msg.scrollIntoView({ behavior: "smooth", block: "end" });
  return msg;
}

// Chunks start with their section heading and keep the Markdown of the help pages
function passageText(source) {
  const lines = source.text.split("\n");
  if (lines[0].trim() === source.section) lines.shift();
  return lines.join("\n").replace(/\*\*/g, "").trim();
}

function renderSources(sources, messageId) {
  const items = sources.map((s) => `
    <div class="source" id="${messageId}-src-${s.n}">
      <div class="source-head">[${s.n}] ${escapeHtml(s.source)} &middot; ${escapeHtml(s.section)}
        <span>similarity ${s.similarity.toFixed(2)}</span></div>
      <p class="source-text">${escapeHtml(passageText(s))}</p>
    </div>`).join("");
  return `<details class="sources"><summary>Sources (${sources.length})</summary>${items}</details>`;
}

function renderAnswer(data, messageId) {
  const cost = data.estimated_cost_usd > 0 ? `$${data.estimated_cost_usd.toFixed(5)}` : "$0";
  const meta = `
    <div class="meta">
      <span>${escapeHtml(data.model)}</span>
      <span>${data.input_tokens} in / ${data.output_tokens} out tokens</span>
      <span>~${cost} at paid-tier prices</span>
      <span>${(data.latency_ms / 1000).toFixed(1)} s</span>
    </div>`;
  return formatAnswer(data.answer, messageId) + meta + renderSources(data.sources, messageId);
}

async function errorMessage(response) {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
  } catch (_) { /* not JSON */ }
  if (response.status === 422) return "The question should be between 3 and 500 characters.";
  return `Something went wrong (HTTP ${response.status}). Please try again.`;
}

let counter = 0;

async function ask(question) {
  const messageId = `m${++counter}`;
  addMessage("user", escapeHtml(question));
  const reply = addMessage("bot", `<p class="thinking">Looking through the help pages...</p>`);
  button.disabled = true;

  // On the free tier a busy model can take a while before the backup one answers
  const status = (text) => {
    const line = reply.querySelector(".thinking");
    if (line) line.textContent = text;
  };
  const timers = [
    setTimeout(() => status("Still working on it..."), 8000),
    setTimeout(() => status("The model is busy, trying a backup one. This can take up to a minute..."), 20000),
  ];

  try {
    const response = await fetch("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
    });
    const html = response.ok
      ? renderAnswer(await response.json(), messageId)
      : `<p class="error">${escapeHtml(await errorMessage(response))}</p>`;
    reply.querySelector(".bubble").innerHTML = html;
  } catch (_) {
    reply.querySelector(".bubble").innerHTML = `<p class="error">Can't reach the server. Check your connection.</p>`;
  } finally {
    timers.forEach(clearTimeout);
    button.disabled = false;
    input.focus();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = input.value.trim();
  if (question.length < 3 || button.disabled) return;
  input.value = "";
  ask(question);
});

thread.addEventListener("click", (event) => {
  const example = event.target.closest(".examples button");
  if (example) {
    if (!button.disabled) ask(example.textContent);
    return;
  }
  const cite = event.target.closest(".cite");
  if (!cite) return;
  const source = document.getElementById(cite.dataset.target);
  if (!source) return;
  source.closest("details").open = true;
  source.scrollIntoView({ behavior: "smooth", block: "center" });
  source.classList.add("highlight");
  setTimeout(() => source.classList.remove("highlight"), 1500);
});
