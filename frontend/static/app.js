const feed = document.getElementById("feed");
const status = document.getElementById("status");

function connect() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${location.host}/ws`);

    ws.onopen = () => {
        status.textContent = "connected";
        status.className = "status connected";
    };

    ws.onclose = () => {
        status.textContent = "disconnected";
        status.className = "status disconnected";
        setTimeout(connect, 3000);
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        addEntry(data);
    };
}

function addEntry(data) {
    const entry = document.createElement("div");
    entry.className = "entry";

    const time = new Date(data.timestamp).toLocaleString();
    const badgeClass = data.status === "error" ? "error" : data.has_issues ? "issues" : "clean";
    const badgeText = data.status === "error" ? "error" : data.has_issues ? "issues found" : "clean";

    entry.innerHTML = `
        <div class="entry-header">
            <strong>${escapeHtml(data.username)}</strong>
            <span>${time}</span>
            <span class="badge ${badgeClass}">${badgeText}</span>
        </div>
        <div class="prompt" onclick="this.classList.toggle('expanded')">${escapeHtml(data.prompt)}</div>
        ${data.has_issues || data.status === "error" ? `<div class="explanation">${DOMPurify.sanitize(marked.parse(data.explanation))}</div>` : ""}
    `;

    feed.prepend(entry);
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

connect();
