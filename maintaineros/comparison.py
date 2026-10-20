from .models import RepositorySnapshot
from .scoring import build_report


def compare(before: RepositorySnapshot, after: RepositorySnapshot):
    if before.full_name != after.full_name:
        raise ValueError("Snapshots must belong to the same repository")
    if before.captured_at > after.captured_at:
        raise ValueError("The before capture must not be newer than the after capture")
    names = (
        "stars",
        "open_issues",
        "open_pull_requests",
        "stale_issues",
        "stale_pull_requests",
        "contributors_last_90_days",
        "top_contributor_share",
        "last_release_days",
    )
    metrics = {
        name: {
            "before": getattr(before, name),
            "after": getattr(after, name),
            "delta": getattr(after, name) - getattr(before, name)
            if getattr(before, name) is not None and getattr(after, name) is not None
            else None,
        }
        for name in names
    }
    old = {(i.kind, i.number): i for i in before.work_items}
    new = {(i.kind, i.number): i for i in after.work_items}
    same_policy = before.policy == after.policy
    same_source = before.source == after.source
    notes = [
        "An item missing from a later sample is no longer observed, not necessarily closed.",
        "Compare coverage notes: the two captures may include different bounded samples.",
    ]
    if not same_policy:
        notes.append(
            "The scoring policy changed. Score and stale-count deltas are not a like-for-like change in project activity."
        )
    if not same_source:
        notes.append("The data source changed between these captures.")
    observed = bool(before.work_items and after.work_items)
    if not observed:
        notes.append(
            "At least one capture has no item-level evidence. Item differences are unavailable."
        )
    return {
        "before": before.captured_at,
        "after": after.captured_at,
        "metrics": metrics,
        "score": {
            "before": build_report(before).score,
            "after": build_report(after).score,
            "delta": build_report(after).score - build_report(before).score,
        },
        "same_policy": same_policy,
        "same_source": same_source,
        "notes": notes,
        "item_comparison_available": observed,
        "newly_observed": [new[key] for key in sorted(new.keys() - old.keys())] if observed else [],
        "no_longer_observed": [old[key] for key in sorted(old.keys() - new.keys())]
        if observed
        else [],
    }
