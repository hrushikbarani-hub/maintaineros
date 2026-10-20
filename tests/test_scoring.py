from app.models import RepositorySnapshot
from app.scoring import build_report


def test_healthy_repository_has_high_score():
    report = build_report(RepositorySnapshot(full_name="a/b", last_release_days=10, contributors_last_90_days=4))
    assert report.status == "healthy"
    assert report.score >= 80


def test_stale_work_is_explained():
    report = build_report(RepositorySnapshot(full_name="a/b", stale_issues=12, stale_pull_requests=6))
    assert report.status == "at_risk"
    assert any(f.category == "reviews" for f in report.findings)

