from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .models import HealthReport, RepositorySnapshot
from .scoring import build_report

app = FastAPI(title="MaintainerOS", version="0.1.0")
snapshots: dict[str, RepositorySnapshot] = {
    "octo-labs/river": RepositorySnapshot(
        full_name="octo-labs/river", description="Async stream toolkit", stars=1240,
        open_issues=34, open_pull_requests=12, stale_issues=7, stale_pull_requests=3,
        contributors_last_90_days=18, top_contributor_share=0.62, last_release_days=42,
    ),
}


@app.get("/api/repositories", response_model=list[RepositorySnapshot])
def list_repositories() -> list[RepositorySnapshot]:
    return list(snapshots.values())


@app.get("/api/repositories/{owner}/{name}/health", response_model=HealthReport)
def repository_health(owner: str, name: str) -> HealthReport:
    key = f"{owner}/{name}"
    snapshot = snapshots.get(key)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Repository snapshot not found")
    return build_report(snapshot)


@app.post("/api/repositories/snapshot", response_model=HealthReport, status_code=201)
def create_snapshot(snapshot: RepositorySnapshot) -> HealthReport:
    snapshots[snapshot.full_name] = snapshot
    return build_report(snapshot)


STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    with open(STATIC_DIR / "index.html", encoding="utf-8") as file:
        return file.read()

