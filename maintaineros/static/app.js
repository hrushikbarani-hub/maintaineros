const $ = (selector) => document.querySelector(selector);
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#039;",
      })[c],
  );
let repositories = [],
  selected = "",
  writeToken = "",
  tokenRequired = false,
  generation = 0;
async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Write-Token": writeToken,
      ...options.headers,
    },
  });
  if (!response.ok) {
    let data;
    try {
      data = await response.json();
    } catch {
      data = {};
    }
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : `Request failed (${response.status}). Check your input.`,
    );
  }
  return response.json();
}
function notice(message, error = false) {
  $("#notice").innerHTML = message
    ? `<div class="notice ${error ? "error" : ""}">${esc(message)}</div>`
    : "";
}
function repoPath(name) {
  return name.split("/").map(encodeURIComponent).join("/");
}
async function refresh() {
  const status = await request("/api/status");
  tokenRequired = status.write_token_required;
  repositories = await request("/api/repositories");
  const findings = repositories.flatMap((r) =>
    r.health.findings.filter(
      (f) => (r.actions[f.category]?.state || "open") === "open",
    ),
  );
  const stats = [
    [
      "Tracked projects",
      repositories.length,
      `${repositories.filter((r) => r.snapshot.source === "demo").length} fictional demo projects`,
    ],
    [
      "Needs attention",
      repositories.filter((r) => r.health.status !== "healthy").length,
      "Based on the latest snapshot",
    ],
    ["Open next steps", findings.length, "Across all tracked repositories"],
    [
      "Waiting for review",
      repositories.reduce((sum, r) => sum + r.snapshot.stale_pull_requests, 0),
      "PRs without updates for 30 days",
    ],
  ];
  $("#summary").innerHTML = stats
    .map(
      ([label, value, note]) =>
        `<div class="stat"><span class="stat-label">${esc(label)}</span><b class="stat-value">${value}</b><span class="stat-note">${esc(note)}</span></div>`,
    )
    .join("");
  $("#repo-count").textContent = repositories.length;
  if (!repositories.some((r) => r.snapshot.full_name === selected))
    selected = repositories[0]?.snapshot.full_name || "";
  renderList();
  if (selected) await renderDetail();
  else
    $("#detail").innerHTML =
      '<div class="empty">Your workbench is ready. Connect a public repository to save your first snapshot and see suggested next steps.</div>';
}
function renderList() {
  $("#repositories").innerHTML = repositories
    .map(
      ({ snapshot: s, health: h }) =>
        `<button class="repo" data-repository="${esc(s.full_name)}" aria-pressed="${s.full_name === selected}"><span class="repo-name">${esc(s.full_name)}</span><p class="repo-desc">${esc(s.description || "No description provided")}</p><span class="repo-foot"><span class="badge ${h.status}">${h.status.replace("_", " ")}</span><span>${s.source === "demo" ? "DEMO · " : ""}${h.score} / 100</span></span></button>`,
    )
    .join("");
}
async function renderDetail() {
  const version = ++generation;
  const repo = repositories.find((r) => r.snapshot.full_name === selected);
  const history = await request(
    `/api/repositories/${repoPath(selected)}/history`,
  );
  if (version !== generation) return;
  const { snapshot: s, health: h, actions } = repo;
  const points = history
    .map(
      (r, i) =>
        `${history.length === 1 ? 250 : (i * 500) / (history.length - 1)},${70 - r.health.score * 0.6}`,
    )
    .join(" ");
  const open = h.findings.filter(
    (f) => (actions[f.category]?.state || "open") === "open",
  ).length;
  $("#detail").innerHTML =
    `<div class="detail-header"><div><h2>${esc(s.full_name)}</h2><p class="detail-sub">${s.source === "demo" ? '<span class="badge demo">Fictional demo</span> · ' : ""}${s.stars.toLocaleString()} stars · ${s.contributors_last_90_days ?? "Unknown"} recent contributors<br>Captured ${esc(new Date(s.captured_at).toLocaleString())}</p></div><div class="big-score">${h.score}<small> /100</small></div></div>
    <figure class="chart"><div class="chart-label"><span>HEALTH OVER TIME</span><span>${history.length} SNAPSHOT${history.length === 1 ? "" : "S"}</span></div><svg viewBox="0 0 500 80" preserveAspectRatio="none" role="img" aria-label="Health scores: ${history.map((r) => r.health.score).join(", ")}"><line x1="0" y1="70" x2="500" y2="70"></line>${history.length === 1 ? `<circle cx="250" cy="${70 - h.score * 0.6}" r="3" fill="#b6ef8b"></circle>` : `<polyline points="${points}"></polyline>`}</svg><figcaption>${esc(new Date(history[0].snapshot.captured_at).toLocaleDateString())} → ${esc(new Date(s.captured_at).toLocaleDateString())} · Higher means fewer measured triage signals</figcaption></figure>
    <div class="actions-heading"><h3>Recommended next steps</h3><span>${open} open</span></div>
    ${
      h.findings
        .map((f) => {
          const state = actions[f.category]?.state || "open";
          return `<article class="finding ${state === "open" ? "" : "done"}"><span class="severity ${f.severity}" aria-label="${f.severity}">◇</span><div class="finding-content"><h4>${esc(f.title)}</h4><p>${esc(f.detail)}</p><p class="next-step">↳ ${esc(f.action)}</p><div class="action-controls">${state === "open" ? `<button class="small-button" data-category="${f.category}" data-state="done">✓ Mark handled</button><button class="small-button" data-category="${f.category}" data-state="dismissed">Dismiss</button>` : `<span class="badge">${state}</span><button class="small-button" data-category="${f.category}" data-state="open">Reopen</button>`}</div></div></article>`;
        })
        .join("") ||
      '<p class="empty">No measured triage signals in this snapshot. Review coverage below before interpreting the score.</p>'
    }
    <details class="coverage"><summary>Data coverage & score methodology</summary><p>Backlog: −2 per stale issue (max 25). Reviews: −4 per stale PR (max 25). Concentration ≥70%: −15. Release older than 180 days: −10. Unknown release and contributor data are not penalized.</p><p>Action states are workbench notes and do not change the score. They persist across snapshots; reopen them when work recurs.</p><ul>${h.coverage_notes.map((note) => `<li>${esc(note)}</li>`).join("")}</ul></details>`;
}
$("#repositories").addEventListener("click", (event) => {
  const button = event.target.closest("[data-repository]");
  if (!button) return;
  selected = button.dataset.repository;
  renderList();
  renderDetail().catch((e) => notice(e.message, true));
});
$("#detail").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-category]");
  if (!button) return;
  if (tokenRequired && !writeToken) {
    notice(
      "Enter your workspace write token in Connect a repository to update actions.",
      true,
    );
    $("#import-dialog").showModal();
    return;
  }
  button.disabled = true;
  try {
    await request(
      `/api/repositories/${repoPath(selected)}/actions/${button.dataset.category}`,
      { method: "PUT", body: JSON.stringify({ state: button.dataset.state }) },
    );
    await refresh();
  } catch (error) {
    notice(error.message, true);
    button.disabled = false;
  }
});
$("#open-import").addEventListener("click", () =>
  $("#import-dialog").showModal(),
);
$("[data-close]").addEventListener("click", () => $("#import-dialog").close());
$("#write-token").addEventListener(
  "input",
  (event) => (writeToken = event.target.value),
);
$("#refresh").addEventListener("click", () =>
  refresh()
    .then(() =>
      notice(
        "Workspace refreshed. Import a repository again to capture newer GitHub activity.",
      ),
    )
    .catch((e) => notice(e.message, true)),
);
$("#import-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#import-submit");
  button.disabled = true;
  button.textContent = "Reading GitHub activity…";
  $("#import-error").textContent = "";
  try {
    const h = await request("/api/import/github", {
      method: "POST",
      body: JSON.stringify({ full_name: $("#repository-name").value.trim() }),
    });
    selected = h.repository;
    await refresh();
    $("#import-dialog").close();
    notice(`Snapshot saved for ${h.repository}.`);
  } catch (error) {
    $("#import-error").textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = "Import activity ↗";
  }
});
refresh().catch((error) => {
  notice(error.message, true);
  $("#detail").innerHTML =
    '<p class="empty">Could not load the workbench. Use Refresh workspace to retry.</p>';
});
