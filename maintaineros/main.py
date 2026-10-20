import csv
import io
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from .demo import seed
from .github import GitHubAdapter, ImportFailure
from .models import ActionUpdate, GitHubImport, RepositorySnapshot
from .scoring import build_report
from .storage import Store

STATIC_DIR = Path(__file__).parent / "static"


def create_app(db_path=None, demo=None, write_token=None, github_factory=None):
    path = db_path or os.getenv("MAINTAINEROS_DB", "data/maintaineros.sqlite3")
    demo = os.getenv("DEMO_DATA", "1") == "1" if demo is None else demo
    token = os.getenv("WRITE_TOKEN", "") if write_token is None else write_token
    store = Store(path)

    @asynccontextmanager
    async def lifespan(app):
        if demo:
            seed(store)
        yield

    app = FastAPI(title="MaintainerOS", version="0.2.0", lifespan=lifespan)
    app.state.store = store

    def authorize(x_write_token: str = Header(default="")):
        if token and not secrets.compare_digest(x_write_token.encode(), token.encode()):
            raise HTTPException(401, "A valid X-Write-Token header is required")

    @app.middleware("http")
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path == "/" or request.url.path.startswith("/static"):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
            )
        return response

    @app.get("/api/status")
    def status():
        return {"ok": True, "version": "0.2.0", "write_token_required": bool(token)}

    @app.get("/api/repositories")
    def repositories():
        return [
            {"snapshot": s, "health": build_report(s), "actions": store.actions(s.full_name)}
            for s in store.latest()
        ]

    def require_repository(owner, name):
        history = store.history(f"{owner}/{name}", 1)
        if not history:
            raise HTTPException(404, "Repository snapshot not found")
        return history[0]

    @app.get("/api/repositories/{owner}/{name}/health")
    def health(owner: str, name: str):
        return build_report(require_repository(owner, name))

    @app.get("/api/repositories/{owner}/{name}/history")
    def history(owner: str, name: str, limit: int = Query(60, ge=1, le=200)):
        require_repository(owner, name)
        return [
            {"snapshot": s, "health": build_report(s)}
            for s in reversed(store.history(f"{owner}/{name}", limit))
        ]

    @app.post("/api/repositories/snapshot", status_code=201, dependencies=[Depends(authorize)])
    def snapshot(snapshot: RepositorySnapshot):
        store.save(snapshot)
        return build_report(snapshot)

    @app.post("/api/import/github", status_code=201, dependencies=[Depends(authorize)])
    def import_github(payload: GitHubImport):
        adapter = github_factory() if github_factory else GitHubAdapter(os.getenv("GITHUB_TOKEN"))
        try:
            snapshot = adapter.snapshot(payload.full_name)
        except ImportFailure as error:
            raise HTTPException(502, str(error)) from error
        store.save(snapshot)
        return build_report(snapshot)

    @app.put(
        "/api/repositories/{owner}/{name}/actions/{category}", dependencies=[Depends(authorize)]
    )
    def update_action(owner: str, name: str, category: str, update: ActionUpdate):
        snapshot = require_repository(owner, name)
        if category not in {"backlog", "reviews", "resilience", "release"}:
            raise HTTPException(422, "Unknown action category")
        store.set_action(snapshot.full_name, category, update)
        return store.actions(snapshot.full_name)

    @app.get("/api/export.csv")
    def export():
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(
            ["repository", "score", "status", "open_issues", "open_prs", "source", "captured_at"]
        )
        for s in store.latest():
            h = build_report(s)
            writer.writerow(
                [
                    s.full_name,
                    h.score,
                    h.status,
                    s.open_issues,
                    s.open_pull_requests,
                    s.source,
                    s.captured_at.isoformat(),
                ]
            )
        return Response(
            output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="maintaineros.csv"'},
        )

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def home():
        return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()
