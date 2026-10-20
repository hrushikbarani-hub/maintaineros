from datetime import UTC, datetime, timedelta

from .models import RepositorySnapshot


def seed(store):
    if store.latest():
        return
    now = datetime.now(UTC)
    examples = [
        ("demo/river", "Async streams for Python applications", 1240, 7, 3, 0.62),
        ("demo/waypoint", "Local-first field notes and mapping", 430, 12, 6, 0.83),
        ("demo/folio", "Accessible document publishing toolkit", 2180, 1, 0, 0.41),
    ]
    for name, description, stars, stale_issues, stale_prs, share in examples:
        for days in (28, 21, 14, 7, 0):
            store.save(
                RepositorySnapshot(
                    full_name=name,
                    description=description,
                    stars=stars,
                    open_issues=34,
                    open_pull_requests=12,
                    stale_issues=min(34, stale_issues + days // 7),
                    stale_pull_requests=min(12, stale_prs + days // 14),
                    contributors_last_90_days=18,
                    top_contributor_share=share,
                    last_release_days=42,
                    captured_at=now - timedelta(days=days),
                    source="demo",
                    coverage_notes=[
                        "Fictional sample repository. Import a public GitHub repository to analyze real activity."
                    ],
                )
            )
