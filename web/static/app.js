// ContextOS front end: no framework. Buttons post forms; long work runs as server-side jobs whose
// progress streams over SSE. Jobs live on the server, so leaving a page and coming back reconnects to them.

function form(data) {
  const f = new FormData();
  for (const [k, v] of Object.entries(data)) f.append(k, v);
  return f;
}

async function post(url, data) {
  const res = await fetch(url, { method: "POST", body: data instanceof FormData ? data : form(data) });
  if (!res.ok) throw new Error((await res.text()) || res.statusText);
  return res;
}

function progressLine(box, text, cls) {
  const div = document.createElement("div");
  div.textContent = text;
  if (cls) div.className = cls;
  box.appendChild(div);
}

// Stream a job's events into a progress box. Events replay from the start, so this also works
// when reconnecting to a job that started before the page loaded.
function watchJob(jobId, box, { intro, onDone, onError } = {}) {
  box.hidden = false;
  box.classList.remove("finished");
  box.innerHTML = "";
  if (intro) progressLine(box, intro);
  const fail = (text) => {
    progressLine(box, text, "err");
    box.classList.add("finished");
    onError && onError();
  };
  const es = new EventSource(`/api/jobs/${jobId}/events`);
  es.onmessage = (ev) => {
    const e = JSON.parse(ev.data);
    if (e.type === "progress" || e.type === "step") {
      progressLine(box, e.text);
    } else if (e.type === "done") {
      es.close();
      box.classList.add("finished");
      onDone && onDone(e.result || {});
    } else if (e.type === "error") {
      es.close();
      fail(e.text);
    }
  };
  es.onerror = () => { es.close(); fail("Lost connection to ContextOS."); };
}

// Start a job (or join the one already running of the same kind) and watch it.
async function startJob(url, data, box, handlers = {}) {
  box.hidden = false;
  box.innerHTML = "";
  progressLine(box, "Starting…");
  try {
    const { job } = await (await post(url, data)).json();
    watchJob(job, box, handlers);
  } catch (e) {
    progressLine(box, e.message, "err");
    box.classList.add("finished");
    handlers.onError && handlers.onError();
  }
}

// ---- Today ---------------------------------------------------------------

function refreshHandlers(btn, windowKind) {
  const box = document.getElementById("progress");
  return {
    onDone: (r) => {
      if (r.empty) {
        progressLine(box, "No messages in this window yet.");
        if (btn) btn.disabled = false;
      } else {
        location.href = `/today?window=${windowKind}`;
      }
    },
    onError: () => btn && (btn.disabled = false),
  };
}

function refresh() {
  const btn = document.getElementById("refresh");
  if (!btn || btn.disabled) return;
  btn.disabled = true;
  const windowKind = btn.dataset.window || "today";
  startJob("/api/refresh", { window: windowKind }, document.getElementById("progress"), refreshHandlers(btn, windowKind));
}

// ---- Ask -----------------------------------------------------------------

const DRAFT_KEY = "contextos.ask.draft";

function askHandlers(question) {
  const f = document.getElementById("ask-form");
  const input = f.querySelector("input[name=question]");
  const btn = f.querySelector("button");
  const box = document.getElementById("ask-progress");
  btn.disabled = input.disabled = true;
  const reset = () => { btn.disabled = input.disabled = false; input.focus(); };
  return {
    intro: `Asking: ${question}`,
    onDone: async (r) => {
      const html = await (await fetch(`/ask/${r.ask_id}/card`)).text();
      document.getElementById("answers").insertAdjacentHTML("afterbegin", html);
      box.hidden = true;
      input.value = "";
      try { sessionStorage.removeItem(DRAFT_KEY); } catch {}
      reset();
    },
    onError: reset,
  };
}

// ---- events --------------------------------------------------------------

document.addEventListener("click", async (ev) => {
  const t = ev.target.closest("button, a");
  if (!t) return;

  if (t.id === "refresh" || t.hasAttribute("data-refresh")) {
    ev.preventDefault();
    return refresh();
  }

  // Done / Tomorrow / Undo and votes on briefing items: swap the card in place.
  const card = t.closest(".item");
  if (card && (t.dataset.action || t.dataset.vote)) {
    ev.preventDefault();
    const base = { digest_id: card.dataset.digest, section: card.dataset.section, key: card.dataset.key };
    const url = t.dataset.action ? "/items/action" : "/items/vote";
    const extra = t.dataset.action ? { action: t.dataset.action } : { vote: t.dataset.vote };
    try {
      card.outerHTML = await (await post(url, { ...base, ...extra })).text();
    } catch (e) {
      alert(e.message);
    }
    return;
  }

  if (t.dataset.suggest) {
    const q = document.getElementById("question");
    if (q && !q.disabled) { q.value = t.dataset.suggest; document.getElementById("ask-form").requestSubmit(); }
    return;
  }

  if (t.id === "sync-now" || t.id === "gmail-connect") {
    t.disabled = true;
    const url = t.id === "sync-now" ? "/api/sync" : "/api/gmail/connect";
    return startJob(url, {}, document.getElementById("progress"),
                    { onDone: () => location.reload(), onError: () => (t.disabled = false) });
  }
});

document.addEventListener("submit", async (ev) => {
  const f = ev.target;

  if (f.matches("[data-missed]")) {
    ev.preventDefault();
    f.outerHTML = await (await post("/feedback/missed", new FormData(f))).text();
  }

  if (f.id === "ask-form") {
    ev.preventDefault();
    const question = f.querySelector("input[name=question]").value.trim();
    if (!question) return;
    startJob("/api/ask", { question }, document.getElementById("ask-progress"), askHandlers(question));
  }
});

// ---- restore state on page load ------------------------------------------

document.addEventListener("DOMContentLoaded", () => {
  // Reconnect to work that is still running on the server.
  for (const box of document.querySelectorAll(".progress[data-job]")) {
    const { job, kind } = box.dataset;
    if (kind === "refresh") {
      const btn = document.getElementById("refresh");
      if (btn) btn.disabled = true;
      watchJob(job, box, refreshHandlers(btn, box.dataset.window || "today"));
    } else if (kind === "ask") {
      const input = document.getElementById("question");
      if (input) input.value = box.dataset.question || "";
      watchJob(job, box, askHandlers(box.dataset.question || ""));
    } else {
      const btn = document.getElementById(kind === "sync" ? "sync-now" : "gmail-connect");
      if (btn) btn.disabled = true;
      watchJob(job, box, { onDone: () => location.reload(), onError: () => btn && (btn.disabled = false) });
    }
  }

  // Keep a half-typed question when switching tabs.
  const input = document.getElementById("question");
  if (input && !input.value) {
    try { input.value = sessionStorage.getItem(DRAFT_KEY) || ""; } catch {}
  }
  input?.addEventListener("input", () => {
    try { sessionStorage.setItem(DRAFT_KEY, input.value); } catch {}
  });
});
