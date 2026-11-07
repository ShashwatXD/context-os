// ContextOS front end: no framework. Buttons post forms; long work streams progress over SSE.

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

// Start a background job and stream its events into a progress box.
async function runJob(url, data, box, { onStep, onDone, onError } = {}) {
  box.hidden = false;
  box.classList.remove("finished");
  box.innerHTML = "";
  const line = (text, cls) => {
    const div = document.createElement("div");
    div.textContent = text;
    if (cls) div.className = cls;
    box.appendChild(div);
  };
  line("Starting…");
  let job;
  try {
    job = (await (await post(url, data)).json()).job;
  } catch (e) {
    line(e.message, "err");
    box.classList.add("finished");
    onError && onError();
    return;
  }
  const es = new EventSource(`/api/jobs/${job}/events`);
  es.onmessage = (ev) => {
    const e = JSON.parse(ev.data);
    if (e.type === "progress" || e.type === "step") {
      line(e.text);
      onStep && onStep(e);
    } else if (e.type === "done") {
      es.close();
      box.classList.add("finished");
      onDone && onDone(e.result || {});
    } else if (e.type === "error") {
      es.close();
      line(e.text, "err");
      box.classList.add("finished");
      onError && onError();
    }
  };
  es.onerror = () => {
    es.close();
    line("Lost connection to ContextOS.", "err");
    box.classList.add("finished");
    onError && onError();
  };
}

// ---- Today ---------------------------------------------------------------

function refresh() {
  const btn = document.getElementById("refresh");
  if (!btn || btn.disabled) return;
  btn.disabled = true;
  const windowKind = btn.dataset.window || "today";
  runJob("/api/refresh", { window: windowKind }, document.getElementById("progress"), {
    onDone: (r) => {
      if (r.empty) {
        document.getElementById("progress").lastChild.textContent = "No messages in this window yet.";
        btn.disabled = false;
      } else {
        location.href = `/today?window=${windowKind}`;
      }
    },
    onError: () => (btn.disabled = false),
  });
}

document.addEventListener("click", async (ev) => {
  const t = ev.target.closest("button, a");
  if (!t) return;

  if (t.id === "refresh" || t.hasAttribute("data-refresh")) {
    ev.preventDefault();
    return refresh();
  }

  // Done / Tomorrow / Undo and 👍 👎 on briefing items: swap the card in place.
  const card = t.closest(".item");
  if (card && (t.dataset.action || t.dataset.vote)) {
    ev.preventDefault();
    const base = { digest_id: card.dataset.digest, section: card.dataset.section, key: card.dataset.key };
    const url = t.dataset.action ? "/items/action" : "/items/vote";
    const extra = t.dataset.action ? { action: t.dataset.action } : { vote: t.dataset.vote };
    try {
      const html = await (await post(url, { ...base, ...extra })).text();
      card.outerHTML = html;
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

  if (t.id === "sync-now") {
    t.disabled = true;
    return runJob("/api/sync", {}, document.getElementById("progress"),
                  { onDone: () => location.reload(), onError: () => (t.disabled = false) });
  }

  if (t.id === "gmail-connect") {
    t.disabled = true;
    return runJob("/api/gmail/connect", {}, document.getElementById("progress"),
                  { onDone: () => location.reload(), onError: () => (t.disabled = false) });
  }
});

document.addEventListener("submit", async (ev) => {
  const f = ev.target;

  if (f.matches("[data-missed]")) {
    ev.preventDefault();
    const html = await (await post("/feedback/missed", new FormData(f))).text();
    f.outerHTML = html;
  }

  if (f.id === "ask-form") {
    ev.preventDefault();
    const input = f.querySelector("input[name=question]");
    const question = input.value.trim();
    if (!question) return;
    const btn = f.querySelector("button");
    btn.disabled = input.disabled = true;
    const box = document.getElementById("ask-progress");
    const reset = () => { btn.disabled = input.disabled = false; input.focus(); };
    await runJob("/api/ask", { question }, box, {
      onDone: async (r) => {
        const html = await (await fetch(`/ask/${r.ask_id}/card`)).text();
        document.getElementById("answers").insertAdjacentHTML("afterbegin", html);
        box.hidden = true;
        input.value = "";
        reset();
      },
      onError: reset,
    });
  }
});
