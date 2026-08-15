const feed = document.getElementById("feed");
const status = document.getElementById("status");
const token = document.querySelector('meta[name="ws-token"]')?.content || "";

// Results already rendered, by id — history is re-fetched on every reconnect,
// so the same result can legitimately arrive twice. Ids are only unique within
// one backend run; currentRun tracks which run they belong to.
const seen = new Set();
let currentRun = null;

// Mirrors ISSUE_TYPES in backend/providers/__init__.py.
const TYPE_LABELS = ["grammar", "spelling", "punctuation", "word-choice", "style"];

// Agents with a colour of their own. Anything else still gets a label, just the
// neutral one — an unrecognised name must never reach the stylesheet.
const AGENT_LABELS = {
    "claude-code": "Claude Code",
    codex: "Codex",
    dashboard: "Dashboard",
};

let historyLoaded = false;
let pending = [];
let ws = null;
let reconnectTimer = null;

// --- Theme -----------------------------------------------------------------
// The stored value is the override; with nothing stored the page follows the OS
// and the CSS media query decides. The button therefore shows what a click
// would switch *to*, resolving the current look from the OS when unset.
const themeToggle = document.getElementById("theme-toggle");

function currentTheme() {
    return (
        document.documentElement.dataset.theme ||
        (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark")
    );
}

function paintToggle() {
    const next = currentTheme() === "dark" ? "light" : "dark";
    themeToggle.textContent = next === "light" ? "☀" : "☾";
    themeToggle.title = `Switch to ${next} theme`;
    themeToggle.setAttribute("aria-label", themeToggle.title);
}

themeToggle.addEventListener("click", () => {
    const next = currentTheme() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
        localStorage.setItem("hoshi-theme", next);
    } catch (e) { /* private mode: the choice just does not survive a reload */ }
    paintToggle();
});

// Only matters while following the OS — once overridden, dataset.theme wins and
// the label is already right.
window
    .matchMedia("(prefers-color-scheme: light)")
    .addEventListener("change", paintToggle);

paintToggle();

// --- Debug view -------------------------------------------------------------
// A body class rather than a re-render: entries already in the feed pick the
// change up through CSS, so toggling never rebuilds the list.
const debugToggle = document.getElementById("debug-toggle");

function debugEnabled() {
    try {
        return localStorage.getItem("hoshi-debug") === "on";
    } catch (e) {
        return false;
    }
}

function paintDebugToggle() {
    const on = debugEnabled();
    document.body.classList.toggle("debug-on", on);
    debugToggle.classList.toggle("active", on);
    debugToggle.title = on ? "Hide debug view" : "Debug view";
    debugToggle.setAttribute("aria-label", debugToggle.title);
}

debugToggle.addEventListener("click", () => {
    try {
        localStorage.setItem("hoshi-debug", debugEnabled() ? "off" : "on");
    } catch (e) { /* private mode: the choice just does not survive a reload */ }
    paintDebugToggle();
});

paintDebugToggle();

function connect() {
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
    // Never stack sockets: connect() is called on load, on close and on wake.
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
        return;
    }

    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws?token=${encodeURIComponent(token)}`);

    ws.onopen = () => {
        status.textContent = "connected";
        status.className = "status connected";
        loadHistory();
    };

    ws.onclose = (event) => {
        status.textContent = "disconnected";
        status.className = "status disconnected";
        historyLoaded = false;
        pending = [];
        if (event.code !== 4401) {
            reconnectTimer = setTimeout(connect, 3000);
        }
    };

    // Buffer live results until history is in, so the feed stays ordered.
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (historyLoaded) {
            addEntry(data);
        } else {
            pending.push(data);
        }
    };
}

async function loadHistory() {
    try {
        const resp = await fetch("/api/results", {
            headers: { Authorization: `Bearer ${token}` },
        });
        if (resp.ok) {
            // Oldest first; each prepend pushes it above the last, so the
            // newest result ends up on top.
            for (const item of await resp.json()) {
                addEntry(item);
            }
        }
    } catch {
        // Server unreachable — live updates still work once it returns.
    }
    historyLoaded = true;
    for (const item of pending) {
        addEntry(item);
    }
    pending = [];
}

// --- Composer: check text typed straight into the dashboard ----------------

const composer = document.getElementById("composer");
const composerInput = document.getElementById("composer-input");
const composerNote = document.getElementById("composer-note");

// Texts submitted but not yet seen coming back, so the note can say what is
// still in flight — a check takes a couple of seconds and silence reads as
// broken. Distinct from `pending`, which buffers websocket messages.
const pendingChecks = new Set();

composer.addEventListener("submit", (event) => {
    event.preventDefault();
    submitCheck();
});

composerInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        submitCheck();
    }
});

async function submitCheck() {
    const text = composerInput.value.trim();
    if (!text) {
        return;
    }
    composerInput.value = "";
    pendingChecks.add(text);
    updateNote();

    try {
        const resp = await fetch("/api/check", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({ prompt: text, project: "dashboard", agent: "dashboard" }),
        });
        if (!resp.ok) {
            failCheck(text, `check failed (${resp.status})`);
        }
    } catch {
        failCheck(text, "check failed — server unreachable");
    }
}

function failCheck(text, message) {
    pendingChecks.delete(text);
    composerNote.textContent = message;
    composerNote.className = "failed";
    // Give the text back, but never clobber something newly typed.
    if (!composerInput.value) {
        composerInput.value = text;
    }
}

function updateNote() {
    composerNote.className = "";
    composerNote.textContent = pendingChecks.size ? `checking ${pendingChecks.size}…` : "";
}

function addEntry(data) {
    // A new run means the backend restarted and its store is empty, so ids
    // start over and whatever is on screen is stale. Drop it and rebuild.
    if (data.run_id && data.run_id !== currentRun) {
        currentRun = data.run_id;
        seen.clear();
        feed.innerHTML = "";
    }
    if (seen.has(data.id)) {
        return;
    }
    seen.add(data.id);

    const entry = document.createElement("div");
    entry.className = "entry";

    const time = new Date(data.timestamp).toLocaleString();
    const badgeClass = data.status === "error" ? "error" : data.has_issues ? "issues" : "clean";
    const badgeText = data.status === "error" ? "error" : data.has_issues ? "issues found" : "clean";

    // Which agent the prompt was typed into. Only known slugs get a colour
    // class; an unknown one is still shown, just escaped and left neutral.
    const agentTag = data.agent
        ? `<span class="agent${
              AGENT_LABELS[data.agent] ? ` agent-${data.agent}` : ""
          }">${escapeHtml(AGENT_LABELS[data.agent] || data.agent)}</span>`
        : "";

    // Types are a fixed server-side vocabulary, but they are rendered as class
    // names, so anything unexpected is dropped rather than injected.
    const types = (data.types || []).filter((t) => TYPE_LABELS.includes(t));
    const typeTags = types
        .map((t) => `<span class="type type-${t}">${t}</span>`)
        .join("");

    // Each finding carries its own type. `explanation` still arrives on the
    // error path, where there are no structured issues to show.
    const issueRows = (data.issues || [])
        .filter((i) => TYPE_LABELS.includes(i.type))
        .map(
            (i) => `<div class="issue">
                <span class="type type-${i.type}">${i.type}</span>
                <span class="issue-note">${DOMPurify.sanitize(marked.parseInline(i.note || ""))}</span>
            </div>`
        )
        .join("");

    // The correction shown as what changed, not as a finished paragraph you
    // have to re-read to spot the edit. Insertions carry the colour of the
    // issue they fix; removals are uniformly struck, since the model marks a
    // survivor beside a deletion rather than the removed words.
    const correctionHtml = (data.diff || []).length
        ? `<div class="correction">${(data.diff || [])
              .map((seg) => {
                  if (seg.op === "equal") {
                      // `after`, not `before`: this is the corrected text, and
                      // its own whitespace is what the separators line up with.
                      return escapeHtml(seg.after);
                  }
                  const typeClass = TYPE_LABELS.includes(seg.type)
                      ? ` ins-${seg.type}`
                      : "";
                  const removed = seg.before
                      ? `<del>${escapeHtml(seg.before)}</del>`
                      : "";
                  const added = seg.after
                      ? `<ins class="ins${typeClass}">${escapeHtml(seg.after)}</ins>`
                      : "";
                  return `${removed}${added}`;
              })
              // Each segment carries the whitespace that followed it, so a line
              // break in the original stays a line break here.
              .map((html, i) => html + escapeHtml(data.diff[i].sep || ""))
              .join("")}</div>`
        : "";

    const fallback =
        !issueRows && !correctionHtml && data.explanation
            ? `<div class="explanation">${DOMPurify.sanitize(marked.parse(data.explanation))}</div>`
            : "";

    const body =
        issueRows || correctionHtml || fallback
            ? `<div class="explanation">${issueRows}${correctionHtml}${fallback}</div>`
            : "";

    // Rendered always, revealed by CSS only under the debug toggle — so the
    // feed never has to be rebuilt when the toggle flips.
    const ghostFlag = data.has_ghost_marks
        ? `<span class="ghost-flag" title="A marked span appears unchanged">!</span>`
        : "";
    const debugLink = `<button type="button" class="debug-link" data-id="${data.id}">debug</button>`;

    entry.innerHTML = `
        <div class="entry-header">
            <strong>${escapeHtml(data.username)}</strong>
            ${agentTag}
            ${data.project ? `<span class="project">${escapeHtml(data.project)}</span>` : ""}
            <span>${time}</span>
            <span class="badge ${badgeClass}">${badgeText}</span>
            ${typeTags}
            ${ghostFlag}
            ${debugLink}
        </div>
        <div class="prompt">${escapeHtml(data.prompt)}</div>
        ${body}
    `;

    feed.prepend(entry);

    // Long prompts are clipped. Offer expansion only when something is actually
    // hidden, and say so — otherwise the explanation discusses sentences that
    // are nowhere on screen, which reads as a broken result rather than a
    // collapsed one. Measured after insertion, when heights are real.
    // Colour each highlight by the issue it fixes, matching that type's tag.
    // The value is checked against the known vocabulary before it becomes a
    // class, so nothing from the model reaches the stylesheet unvetted.
    entry.querySelectorAll(".correction mark").forEach((m) => {
        if (TYPE_LABELS.includes(m.dataset.type)) {
            m.classList.add(`mark-${m.dataset.type}`);
        }
    });

    const promptEl = entry.querySelector(".prompt");
    promptEl.addEventListener("click", () => promptEl.classList.toggle("expanded"));
    if (promptEl.scrollHeight > promptEl.clientHeight + 1) {
        promptEl.classList.add("clipped");
    }

    if (pendingChecks.delete(data.prompt)) {
        updateNote();
    }
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// Coming back to the tab is the moment staleness gets noticed, and a socket
// killed by sleep or a network change may never fire onclose. Reconnect at once
// rather than waiting out the retry timer, and otherwise re-sync history in case
// anything was missed while hidden.
document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
        return;
    }
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        connect();
    } else {
        loadHistory();
    }
});

connect();

// One listener on the feed rather than one per entry: entries are prepended
// continuously, and a delegated handler covers the ones not yet created.
feed.addEventListener("click", async (event) => {
    const link = event.target.closest(".debug-link");
    if (!link) {
        return;
    }
    const entry = link.closest(".entry");
    const existing = entry.querySelector(".debug-panel");
    if (existing) {
        existing.remove();
        return;
    }

    const panel = document.createElement("div");
    panel.className = "debug-panel";
    panel.textContent = "loading…";
    entry.appendChild(panel);

    try {
        const resp = await fetch(`/api/results/${link.dataset.id}/debug`, {
            headers: { Authorization: `Bearer ${token}` },
        });
        if (!resp.ok) {
            panel.textContent = `debug unavailable (${resp.status})`;
            return;
        }
        panel.innerHTML = renderDebug(await resp.json());
    } catch (e) {
        panel.textContent = `debug unavailable (${e.message})`;
    }
});

function renderDebug(debug) {
    const analysis = debug.analysis || {};
    const ghosts = analysis.ghost_marks || [];

    // Worded as an observation, not a verdict: word alignment is a heuristic,
    // and nothing in the pipeline acts on it.
    let verdict = "";
    if (analysis.no_op) {
        verdict = "the correction is identical to the original — nothing changed";
    } else if (ghosts.length) {
        const words = ghosts.map((g) => `“${escapeHtml(g.text)}”`).join(", ");
        verdict = `${ghosts.length} marked span${ghosts.length > 1 ? "s appear" : " appears"} unchanged: ${words}`;
    }
    const analysisHtml = verdict
        ? `<div class="debug-verdict">${verdict}</div>`
        : `<div class="debug-ok">every marked span matches a real change</div>`;

    // No diff here: the entry above now shows it, and repeating it in the panel
    // only invites the two renderings to drift apart.
    const request = debug.request || {};
    const timing = debug.timing || {};
    const usage = timing.usage || {};
    const meta = [
        request.provider,
        request.model,
        request.system_prompt_hash ? `prompt ${request.system_prompt_hash}` : "",
        timing.latency_ms !== undefined ? `${(timing.latency_ms / 1000).toFixed(1)}s` : "",
        usage.input !== undefined ? `${usage.input} in / ${usage.output} out` : "",
    ]
        .filter(Boolean)
        .map(escapeHtml)
        .join(" · ");

    const dropped = (debug.derived || {}).dropped_issues || [];
    const droppedHtml = dropped.length
        ? `<div class="debug-dropped">${dropped.length} issue${dropped.length > 1 ? "s" : ""} dropped as an unknown type: ${dropped
              .map((i) => escapeHtml(i.type))
              .join(", ")}</div>`
        : "";

    const errorHtml = debug.error
        ? `<div class="debug-verdict">${escapeHtml(debug.error.type)}: ${escapeHtml(debug.error.message)}</div>`
        : "";

    return `
        ${errorHtml}
        ${debug.error ? "" : analysisHtml}
        ${droppedHtml}
        <div class="debug-meta">${meta}</div>
        <pre class="debug-raw">${escapeHtml(JSON.stringify(debug.raw || {}, null, 2))}</pre>
    `;
}
