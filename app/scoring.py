from .models import Finding, HealthReport, RepositorySnapshot


def build_report(snapshot: RepositorySnapshot) -> HealthReport:
    """Produce a deliberately explainable score, not a black-box prediction."""
    score = 100
    findings: list[Finding] = []

    if snapshot.stale_issues:
        penalty = min(25, snapshot.stale_issues * 2)
        score -= penalty
        findings.append(Finding(
            severity="warning" if snapshot.stale_issues < 10 else "critical",
            category="backlog",
            title=f"{snapshot.stale_issues} issues may be stale",
            detail="Issues without recent activity can hide bugs and frustrate contributors.",
            action="Review, close, or add a clear next step to stale issues.",
        ))

    if snapshot.stale_pull_requests:
        score -= min(25, snapshot.stale_pull_requests * 4)
        findings.append(Finding(
            severity="critical" if snapshot.stale_pull_requests >= 5 else "warning",
            category="reviews",
            title=f"{snapshot.stale_pull_requests} pull requests need attention",
            detail="Long-lived pull requests increase contributor drop-off and merge conflicts.",
            action="Assign reviewers or comment with a concrete decision path.",
        ))

    if snapshot.top_contributor_share >= 0.7 and snapshot.contributors_last_90_days > 1:
        score -= 15
        findings.append(Finding(
            severity="warning",
            category="resilience",
            title="Contribution concentration is high",
            detail=f"The top contributor accounts for {snapshot.top_contributor_share:.0%} of recent activity.",
            action="Document ownership and create beginner-friendly issues.",
        ))

    if snapshot.last_release_days is None or snapshot.last_release_days > 180:
        score -= 10
        findings.append(Finding(
            severity="info",
            category="release",
            title="Release cadence is unclear",
            detail="No release in the last six months was recorded for this snapshot.",
            action="Publish a release or document the project's release policy.",
        ))

    score = max(0, min(100, score))
    status = "healthy" if score >= 80 else "watch" if score >= 60 else "at_risk"
    return HealthReport(
        repository=snapshot.full_name,
        score=score,
        status=status,
        findings=findings,
        captured_at=snapshot.captured_at,
    )

