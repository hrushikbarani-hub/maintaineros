import hashlib
from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient

from maintaineros.comparison import compare
from maintaineros.github import GitHubAdapter
from maintaineros.main import create_app
from maintaineros.models import RepositorySnapshot, TriagePolicy
from maintaineros.scoring import build_report
from maintaineros.storage import Store


def test_policy_persists_without_rescoring_old_snapshots(tmp_path):
    path = tmp_path / "db"
    original = RepositorySnapshot(
        full_name="team/project", top_contributor_share=0.8, last_release_days=200
    )
    store = Store(path)
    store.save(original)
    store.set_policy(
        original.full_name, TriagePolicy(concentration_threshold=0.9, check_releases=False)
    )
    restarted = Store(path)
    assert restarted.policy("TEAM/PROJECT").concentration_threshold == 0.9
    captured = restarted.latest()[0]
    assert build_report(captured).score == 75
    assert captured.policy == TriagePolicy()
    assert (
        build_report(
            original.model_copy(update={"policy": restarted.policy(original.full_name)})
        ).score
        == 100
    )


def test_github_import_uses_configured_stale_boundary():
    def response(request):
        if request.url.path.endswith("/issues"):
            return httpx.Response(
                200,
                json=[
                    {
                        "number": 1,
                        "title": "Issue",
                        "updated_at": (datetime.now(UTC) - timedelta(days=40)).isoformat(),
                    }
                ],
            )
        if request.url.path.endswith("/commits"):
            return httpx.Response(200, json=[])
        if request.url.path.endswith("/releases/latest"):
            return httpx.Response(404)
        return httpx.Response(200, json={"full_name": "team/project", "stargazers_count": 0})

    capture = GitHubAdapter(transport=httpx.MockTransport(response)).snapshot(
        "team/project", policy=TriagePolicy(stale_days=60)
    )
    assert capture.stale_issues == 0
    assert capture.policy.stale_days == 60
    assert "60 days" in capture.coverage_notes[0]


def test_compare_accounts_for_missing_values_and_changed_policy():
    now = datetime.now(UTC)
    item = dict(number=1, title="Issue", kind="issue", updated_at=now)
    old = RepositorySnapshot(
        full_name="team/project",
        stars=5,
        captured_at=now,
        contributors_last_90_days=None,
        work_items=[item],
    )
    new = old.model_copy(
        update={
            "stars": 10,
            "captured_at": now + timedelta(days=1),
            "policy": TriagePolicy(check_releases=False),
        }
    )
    result = compare(old, new)
    assert result["metrics"]["stars"]["delta"] == 5
    assert result["metrics"]["contributors_last_90_days"]["delta"] is None
    assert result["same_policy"] is False
    assert any("not a like-for-like" in note for note in result["notes"])


def test_snapshot_ids_scoped_comparison_and_policy_auth(tmp_path):
    with TestClient(create_app(tmp_path / "db", demo=False, write_token="token")) as client:
        headers = {"X-Write-Token": "token"}
        first = RepositorySnapshot(
            full_name="team/project", captured_at=datetime(2026, 1, 1, tzinfo=UTC)
        )
        second = first.model_copy(
            update={"stars": 20, "captured_at": datetime(2026, 2, 1, tzinfo=UTC)}
        )
        for s in (first, second):
            assert (
                client.post(
                    "/api/repositories/snapshot", json=s.model_dump(mode="json"), headers=headers
                ).status_code
                == 201
            )
        history = client.get("/api/repositories/team/project/history").json()
        ids = [s["id"] for s in history]
        result = client.get(
            "/api/repositories/team/project/compare", params={"before": ids[0], "after": ids[1]}
        )
        assert result.json()["metrics"]["stars"]["delta"] == 20
        assert result.json()["item_comparison_available"] is False
        assert (
            client.get(
                "/api/repositories/team/project/compare", params={"before": ids[1], "after": ids[0]}
            ).status_code
            == 422
        )
        assert (
            client.get(
                "/api/repositories/other/project/compare",
                params={"before": ids[0], "after": ids[1]},
            ).status_code
            == 404
        )
        policy = TriagePolicy(stale_days=90).model_dump()
        url = "/api/repositories/team/project/policy"
        assert client.put(url, json=policy).status_code == 401
        assert client.put(url, json=policy, headers=headers).status_code == 200
        assert client.get(url).json()["stale_days"] == 90
        assert (
            client.get("/api/repositories/team/project/health").json()["policy"]["stale_days"] == 30
        )
        policy["stale_days"] = 0
        assert client.put(url, json=policy, headers=headers).status_code == 422


def test_legacy_snapshot_keeps_stored_identity(tmp_path):
    store = Store(tmp_path / "db")
    snapshot = RepositorySnapshot(full_name="team/project")
    legacy_payload = snapshot.model_dump_json(exclude={"policy", "work_items"})
    digest = hashlib.sha256(legacy_payload.encode()).hexdigest()
    with store.connection() as db:
        db.execute(
            "INSERT INTO snapshots(digest,repository,captured_at,payload) VALUES(?,?,?,?)",
            (digest, snapshot.full_name, snapshot.captured_at.isoformat(), legacy_payload),
        )
    identifier, restored = store.history_entries("team/project")[0]
    assert identifier == digest
    assert restored.policy == TriagePolicy()
    assert store.find_snapshot("team/project", identifier) == restored


def test_policy_boundaries_and_disabled_checks():
    snapshot = RepositorySnapshot(
        full_name="team/project", top_contributor_share=0.7, last_release_days=180
    )
    assert build_report(snapshot).score == 85  # Concentration inclusive; release strictly older.
    snapshot.policy = TriagePolicy(concentration_threshold=0.8)
    assert build_report(snapshot).score == 100
    snapshot.last_release_days = 181
    assert build_report(snapshot).score == 90
    snapshot.policy = TriagePolicy(check_releases=False, check_concentration=False)
    assert build_report(snapshot).score == 100


def test_observed_item_changes_do_not_claim_closure():
    now = datetime.now(UTC)
    item = dict(number=1, title="Earlier item", kind="issue", updated_at=now)
    before = RepositorySnapshot(full_name="team/project", work_items=[item], captured_at=now)
    after = before.model_copy(
        update={
            "captured_at": now + timedelta(days=1),
            "work_items": [before.work_items[0].model_copy(update={"number": 2})],
        }
    )
    result = compare(before, after)
    assert result["item_comparison_available"]
    assert result["newly_observed"][0].number == 2
    assert result["no_longer_observed"][0].number == 1
    assert any("not necessarily closed" in note for note in result["notes"])
