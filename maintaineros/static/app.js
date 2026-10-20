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
  generation = 0,
  policyTarget = "";
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
      "Using each capture’s stale threshold",
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
function evidenceFor(snapshot, category) {
  const kind =
    category === "backlog"
      ? "issue"
      : category === "reviews"
        ? "pull_request"
        : null;
  if (!kind) return "";
  const captured = new Date(snapshot.captured_at).getTime();
  const evidence = (snapshot.work_items || [])
    .filter(
      (item) =>
        item.kind === kind &&
        captured - new Date(item.updated_at).getTime() >
          (snapshot.policy?.stale_days || 30) * 86400000,
    )
    .sort((a, b) => new Date(a.updated_at) - new Date(b.updated_at));
  if (!evidence.length) return "";
  return `<ul class="evidence">${evidence
    .slice(0, 5)
    .map((item) => {
      const text = `#${item.number} ${esc(item.title)}`;
      const age = Math.floor(
        (captured - new Date(item.updated_at).getTime()) / 86400000,
      );
      const url = `https://github.com/${repoPath(snapshot.full_name)}/${kind === "issue" ? "issues" : "pull"}/${item.number}`;
      return `<li>${snapshot.source === "demo" ? `<span>${text} · sample</span>` : `<a href="${url}" target="_blank" rel="noopener noreferrer">${text} ↗</a>`}<small>${age}d without an update at capture</small></li>`;
    })
    .join(
      "",
    )}</ul>${evidence.length > 5 ? `<p>Showing 5 of ${evidence.length} sampled stale ${kind === "issue" ? "issues" : "PRs"}.</p>` : ""}`;
}
async function renderDetail() {
  const version = ++generation;
  const repo = repositories.find((r) => r.snapshot.full_name === selected);
  const history = await request(
    `/api/repositories/${repoPath(selected)}/history`,
  );
  if (version !== generation) return;
  const { snapshot: s, health: h, actions } = repo;
  const p = s.policy || {
    stale_days: 30,
    release_gap_days: 180,
    concentration_threshold: 0.7,
    check_releases: true,
    check_concentration: true,
  };
  const options = history
    .map(
      (entry, index) =>
        `<option value="${entry.id}">${esc(new Date(entry.snapshot.captured_at).toLocaleString())} · ${entry.health.score}/100 · ${index + 1}</option>`,
    )
    .join("");
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
    <figure class="chart"><div class="chart-label"><span>HEALTH OVER TIME</span><span>${history.length} SNAPSHOT${history.length === 1 ? "" : "S"}</span></div><svg viewBox="0 0 500 80" preserveAspectRatio="none" role="img" aria-label="Health scores: ${history.map((r) => r.health.score).join(", ")}"><line x1="0" y1="70" x2="500" y2="70"></line>${history.length === 1 ? `<circle cx="250" cy="${70 - h.score * 0.6}" r="3" fill="#b6ef8b"></circle>` : `<polyline points="${points}"></polyline>`}</svg><figcaption>${esc(new Date(history[0].snapshot.captured_at).toLocaleDateString())} → ${esc(new Date(s.captured_at).toLocaleDateString())} · Each score uses its capture’s policy and coverage</figcaption></figure>
    <div class="capture-tools"><button class="small-button" data-policy>Configure capture policy</button><span>Captured with ${p.stale_days}d stale threshold</span></div>
    ${history.length > 1 ? `<details class="comparison"><summary>Compare saved captures</summary><div class="compare-inputs"><label>Before<select id="compare-before">${options}</select></label><label>After<select id="compare-after">${options}</select></label></div><button class="small-button" data-compare>Compare activity</button><div id="comparison-result" aria-live="polite"></div></details>` : ""}
    <div class="actions-heading"><h3>Recommended next steps</h3><span>${open} open</span></div>
    ${
      h.findings
        .map((f) => {
          const state = actions[f.category]?.state || "open";
          return `<article class="finding ${state === "open" ? "" : "done"}"><span class="severity ${f.severity}" aria-label="${f.severity}">◇</span><div class="finding-content"><h4>${esc(f.title)}</h4><p>${esc(f.detail)}</p><p class="next-step">↳ ${esc(f.action)}</p>${evidenceFor(s, f.category)}<div class="action-controls">${state === "open" ? `<button class="small-button" data-category="${f.category}" data-state="done">✓ Mark handled</button><button class="small-button" data-category="${f.category}" data-state="dismissed">Dismiss</button>` : `<span class="badge">${state}</span><button class="small-button" data-category="${f.category}" data-state="open">Reopen</button>`}</div></div></article>`;
        })
        .join("") ||
      '<p class="empty">No measured triage signals in this snapshot. Review coverage below before interpreting the score.</p>'
    }
    <details class="coverage"><summary>Data coverage & score methodology</summary><p>This capture: stale after ${p.stale_days} days. Backlog: −2 per stale issue (max 25). Reviews: −4 per stale PR (max 25). ${p.check_concentration ? `Concentration ≥${Math.round(p.concentration_threshold * 100)}%: −15.` : "Concentration check disabled."} ${p.check_releases ? `Release older than ${p.release_gap_days} days: −10.` : "Release check disabled."} Unknown release and contributor data are not penalized.</p><p>History scores use each capture’s saved policy. Action states are workbench notes and do not change the score. They persist across snapshots; reopen them when work recurs.</p><ul>${h.coverage_notes.map((note) => `<li>${esc(note)}</li>`).join("")}</ul></details>`;
  if ($("#compare-after")) $("#compare-after").value = history.at(-1).id;
}
function openPolicy() {
  const repo = repositories.find((r) => r.snapshot.full_name === selected);
  const p = repo.capture_policy || repo.snapshot.policy;
  policyTarget = selected;
  $("#policy-project").textContent = selected;
  $("#stale-days").value = p.stale_days;
  $("#release-days").value = p.release_gap_days;
  $("#concentration").value = p.concentration_threshold * 100;
  $("#check-releases").checked = p.check_releases;
  $("#check-concentration").checked = p.check_concentration;
  $("#policy-token").value = writeToken;
  $("#policy-error").textContent = "";
  $("#policy-dialog").showModal();
}
async function compareCaptures(button) {
  const view = generation,
    name = selected;
  const query = new URLSearchParams({
    before: $("#compare-before").value,
    after: $("#compare-after").value,
  });
  button.disabled = true;
  try {
    const result = await request(
      `/api/repositories/${repoPath(name)}/compare?${query}`,
    );
    if (view !== generation) return;
    const labels = {
      stars: "Stars",
      open_issues: "Open issues",
      open_pull_requests: "Open PRs",
      stale_issues: "Stale issues",
      stale_pull_requests: "Stale PRs",
      contributors_last_90_days: "Contributors",
      last_release_days: "Release age (days)",
    };
    $("#comparison-result").innerHTML =
      `<p>Score: ${result.score.before} → ${result.score.after} (${result.score.delta >= 0 ? "+" : ""}${result.score.delta})</p><table><thead><tr><th>Metric</th><th>Before</th><th>After</th><th>Change</th></tr></thead><tbody>${Object.entries(
        labels,
      )
        .map(([key, label]) => {
          const m = result.metrics[key];
          return `<tr><th>${label}</th><td>${m.before ?? "Unknown"}</td><td>${m.after ?? "Unknown"}</td><td>${m.delta === null ? "—" : (m.delta > 0 ? "+" : "") + m.delta}</td></tr>`;
        })
        .join(
          "",
        )}</tbody></table>${result.item_comparison_available ? `<p>${result.newly_observed.length} newly observed items · ${result.no_longer_observed.length} no longer observed</p>` : ""}<ul>${result.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>`;
  } catch (error) {
    if (view === generation)
      $("#comparison-result").textContent = error.message;
  } finally {
    button.disabled = false;
  }
}
$("#repositories").addEventListener("click", (event) => {
  const button = event.target.closest("[data-repository]");
  if (!button) return;
  selected = button.dataset.repository;
  renderList();
  renderDetail().catch((e) => notice(e.message, true));
});
$("#detail").addEventListener("click", async (event) => {
  if (event.target.closest("[data-policy]")) {
    openPolicy();
    return;
  }
  const compareButton = event.target.closest("[data-compare]");
  if (compareButton) {
    await compareCaptures(compareButton);
    return;
  }
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
document
  .querySelectorAll("[data-close]")
  .forEach((button) =>
    button.addEventListener("click", () => button.closest("dialog").close()),
  );
$("#policy-token").addEventListener("input", (event) => {
  writeToken = event.target.value;
  $("#write-token").value = writeToken;
});
$("#policy-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("#save-policy");
  button.disabled = true;
  $("#policy-error").textContent = "";
  const policy = {
    stale_days: Number($("#stale-days").value),
    release_gap_days: Number($("#release-days").value),
    concentration_threshold: Number($("#concentration").value) / 100,
    check_releases: $("#check-releases").checked,
    check_concentration: $("#check-concentration").checked,
  };
  try {
    await request(`/api/repositories/${repoPath(policyTarget)}/policy`, {
      method: "PUT",
      body: JSON.stringify(policy),
    });
    await refresh();
    $("#policy-dialog").close();
    notice(
      "Policy saved. Import this repository again to capture activity with the new thresholds. Historical scores are unchanged.",
    );
  } catch (error) {
    $("#policy-error").textContent = error.message;
  } finally {
    button.disabled = false;
  }
});
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
