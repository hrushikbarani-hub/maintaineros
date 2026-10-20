# MaintainerOS

MaintainerOS is an open-source project health dashboard for maintainers. It turns repository activity into actionable signals: stale work, review bottlenecks, release readiness, and contributor concentration.

## Current slice

- FastAPI JSON API with repository snapshots and health scoring
- Browser dashboard built with plain JavaScript (no build step)
- Transparent scoring rules with explainable findings
- Adapter boundary ready for GitHub GraphQL/API ingestion
- Unit tests, Dockerfile, and a local demo dataset

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. The API is documented at `/docs`.

## Roadmap

1. GitHub App ingestion and scheduled snapshots
2. PostgreSQL persistence and historical trend charts
3. Pull-request review recommendations
4. Public health pages and embeddable badges
5. GitHub Actions integration for regression checks

