from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from maintaineros.github import GitHubAdapter, ImportFailure
from maintaineros.main import create_app
from maintaineros.models import RepositorySnapshot
from maintaineros.scoring import build_report
from maintaineros.storage import Store


def snapshot(**values):
    return RepositorySnapshot(
        full_name="team/project", open_issues=40, open_pull_requests=10, **values
    )


def test_scoring_explains_penalties_and_unknowns():
    healthy = build_report(snapshot())
    assert healthy.score == 100  # Unknown release/contributors are not fabricated.
    report = build_report(
        snapshot(
            stale_issues=12, stale_pull_requests=6, top_contributor_share=0.8, last_release_days=200
        )
    )
    assert report.score == 27
    assert {f.category for f in report.findings} == {"backlog", "reviews", "resilience", "release"}


@pytest.mark.parametrize(
    "values",
    [
        {"stale_issues": 41},
        {"stale_pull_requests": 11},
        {"top_contributor_share": 1.5},
        {"stars": -1},
    ],
)
def test_impossible_metrics_rejected(values):
    with pytest.raises(ValidationError):
        snapshot(**values)


def test_snapshots_survive_restart_and_duplicate_import(tmp_path):
    path = tmp_path / "data.db"
    first = snapshot(captured_at=datetime(2026, 1, 1, tzinfo=UTC))
    later = snapshot(captured_at=datetime(2026, 2, 1, tzinfo=UTC), stars=42)
    store = Store(path)
    store.save(later)
    store.save(first)
    store.save(first)
    restarted = Store(path)
    assert len(restarted.history("Team/Project")) == 2
    assert restarted.latest()[0].stars == 42


def test_api_actions_history_and_write_token(tmp_path):
    path = tmp_path / "data.db"
    with TestClient(create_app(path, demo=False, write_token="test-token")) as client:
        assert (
            client.post(
                "/api/repositories/snapshot", json=snapshot().model_dump(mode="json")
            ).status_code
            == 401
        )
        headers = {"X-Write-Token": "test-token"}
        assert (
            client.post(
                "/api/repositories/snapshot",
                json=snapshot(stale_issues=5).model_dump(mode="json"),
                headers=headers,
            ).status_code
            == 201
        )
        result = client.put(
            "/api/repositories/team/project/actions/backlog",
            json={"state": "done", "note": "Reviewed"},
            headers=headers,
        )
        assert result.json()["backlog"]["state"] == "done"
        assert (
            client.put(
                "/api/repositories/team/project/actions/made-up",
                json={"state": "done"},
                headers=headers,
            ).status_code
            == 422
        )
        assert len(client.get("/api/repositories/team/project/history").json()) == 1
        assert client.get("/api/repositories/no/such/health").status_code == 404
        assert client.get("/api/export.csv").headers["content-type"].startswith("text/csv")
        assert client.get("/").headers["content-security-policy"].startswith("default-src 'self'")
    with TestClient(create_app(path, demo=False)) as client:
        assert client.get("/api/repositories").json()[0]["actions"]["backlog"]["note"] == "Reviewed"


def test_github_adapter_maps_public_data_and_paginates():
    now = datetime.now(UTC)
    stale = (now - timedelta(days=40)).isoformat()
    seen = []

    def handler(request):
        seen.append(str(request.url))
        assert request.url.host == "api.github.com"
        path = request.url.path
        if path.endswith("/issues"):
            page = request.url.params["page"]
            return httpx.Response(
                200,
                json=[
                    {"number": n, "title": f"Issue {n}", "updated_at": stale} for n in range(1, 101)
                ]
                if page == "1"
                else [
                    {
                        "number": 101,
                        "title": "Review this PR",
                        "updated_at": stale,
                        "pull_request": {},
                    }
                ],
            )
        if path.endswith("/commits"):
            return httpx.Response(
                200,
                json=[
                    {"author": {"login": "alice", "type": "User"}},
                    {"author": {"login": "bot", "type": "Bot"}},
                ],
            )
        if path.endswith("/releases/latest"):
            return httpx.Response(404)
        return httpx.Response(
            200,
            json={
                "full_name": "team/project",
                "private": False,
                "description": "Useful",
                "stargazers_count": 7,
            },
        )

    data = GitHubAdapter(transport=httpx.MockTransport(handler)).snapshot("team/project")
    assert data.open_issues == 100 and data.stale_pull_requests == 1
    assert data.contributors_last_90_days == 1 and data.top_contributor_share == 1
    assert any("page=2" in url for url in seen)
    assert data.last_release_days is None
    assert len(data.work_items) == 101
    assert data.work_items[-1].kind == "pull_request"
    assert data.work_items[-1].number == 101


def test_work_item_evidence_survives_restart_and_old_snapshots_still_load(tmp_path):
    old = snapshot().model_dump(mode="json")
    old.pop("work_items")
    assert RepositorySnapshot.model_validate(old).work_items == []
    record = snapshot(
        work_items=[
            {
                "number": 42,
                "title": "A stalled bug",
                "kind": "issue",
                "updated_at": datetime(2026, 1, 1, tzinfo=UTC),
            }
        ]
    )
    Store(tmp_path / "db").save(record)
    assert (
        Store(tmp_path / "db").history(record.full_name)[0].work_items[0].title == "A stalled bug"
    )


def test_rate_limit_message_never_exposes_credentials():
    adapter = GitHubAdapter(
        token="secret-token", transport=httpx.MockTransport(lambda r: httpx.Response(403))
    )
    with pytest.raises(ImportFailure) as error:
        adapter.snapshot("team/project")
    assert "secret-token" not in str(error.value)
    assert "rate limit" in str(error.value)


def test_failed_github_import_does_not_save(tmp_path):
    class FailingAdapter:
        def snapshot(self, name):
            raise ImportFailure("Temporary outage")

    with TestClient(
        create_app(tmp_path / "db", demo=False, github_factory=FailingAdapter)
    ) as client:
        assert (
            client.post("/api/import/github", json={"full_name": "team/project"}).status_code == 502
        )
        assert client.get("/api/repositories").json() == []


def test_successful_github_import_persists(tmp_path):
    class FakeAdapter:
        def snapshot(self, name):
            return snapshot(source="github", stars=123)

    with TestClient(create_app(tmp_path / "db", demo=False, github_factory=FakeAdapter)) as client:
        assert (
            client.post("/api/import/github", json={"full_name": "team/project"}).status_code == 201
        )
        assert client.get("/api/repositories").json()[0]["snapshot"]["stars"] == 123
