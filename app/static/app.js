const app = document.querySelector('#app');
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
async function load() {
  const repositories = await fetch('/api/repositories').then(r => r.json());
  app.innerHTML = '';
  for (const repo of repositories) {
    const health = await fetch(`/api/repositories/${repo.full_name}/health`).then(r => r.json());
    const findings = health.findings.map(f => `<li class="finding ${f.severity}"><strong>${escapeHtml(f.title)}</strong><span>${escapeHtml(f.action)}</span></li>`).join('');
    app.insertAdjacentHTML('beforeend', `<article class="card"><div class="card-top"><div><h2>${escapeHtml(repo.full_name)}</h2><p>${escapeHtml(repo.description)}</p></div><div class="score ${health.status}">${health.score}<small>/100</small></div></div><div class="metrics"><span><b>${repo.stars}</b> stars</span><span><b>${repo.open_pull_requests}</b> open PRs</span><span><b>${repo.contributors_last_90_days}</b> contributors</span></div><h3>Recommended actions</h3><ul>${findings || '<li class="finding info">No issues detected.</li>'}</ul></article>`);
  }
}
load().catch(error => app.innerHTML = `<p class="error">Unable to load dashboard: ${escapeHtml(error.message)}</p>`);

