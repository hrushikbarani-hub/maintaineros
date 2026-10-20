"""Read public GitHub metadata only. All outbound requests have a fixed API origin."""

from collections import Counter
from datetime import UTC, datetime, timedelta

import httpx

from .models import RepositorySnapshot, WorkItem


class ImportFailure(Exception):
    pass


class GitHubAdapter:
    def __init__(self, token: str | None = None, transport=None):
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "MaintainerOS/0.2"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = httpx.Client(
            base_url="https://api.github.com",
            headers=headers,
            timeout=httpx.Timeout(15, connect=5),
            follow_redirects=False,
            transport=transport,
        )

    def get(self, path, params=None, allow_missing=False):
        response = self.client.get(path, params=params)
        if allow_missing and response.status_code == 404:
            return None
        if response.status_code == 409 and path.endswith("/commits"):
            return []  # GitHub uses 409 for repositories with no commits yet.
        if response.status_code in (403, 429):
            raise ImportFailure(
                "GitHub rate limit or access restriction. Try later or configure a server-side GITHUB_TOKEN."
            )
        if response.status_code != 200:
            raise ImportFailure(
                f"GitHub returned {response.status_code}. Check that this public repository exists."
            )
        return response.json()

    def pages(self, path, params=None, cap=5):
        data = []
        for page in range(1, cap + 1):
            batch = self.get(path, {**(params or {}), "per_page": 100, "page": page})
            data.extend(batch)
            if len(batch) < 100:
                return data, False
        return data, True

    def snapshot(self, name: str) -> RepositorySnapshot:
        try:
            now = datetime.now(UTC)
            metadata = self.get(f"/repos/{name}")
            if metadata.get("private"):
                raise ImportFailure("This version imports public repositories only.")
            canonical = metadata["full_name"]
            path = f"/repos/{canonical}"
            issues, issue_cap = self.pages(
                f"{path}/issues", {"state": "open", "sort": "updated", "direction": "desc"}
            )
            commits, commit_cap = self.pages(
                f"{path}/commits", {"since": (now - timedelta(days=90)).isoformat()}
            )
            release = self.get(f"{path}/releases/latest", allow_missing=True)
            counts = Counter(
                c["author"]["login"]
                for c in commits
                if c.get("author") and c["author"].get("type") != "Bot"
            )
            tracked_issues = [i for i in issues if "pull_request" not in i]
            prs = [i for i in issues if "pull_request" in i]
            cutoff = now - timedelta(days=30)

            def stale(rows):
                return sum(
                    datetime.fromisoformat(i["updated_at"].replace("Z", "+00:00")) < cutoff
                    for i in rows
                )

            notes = [
                "Stale means no update for 30 days. Contributor concentration uses commits linked to non-bot GitHub accounts in the last 90 days.",
                "Score is a triage heuristic, not a quality ranking. Release expectations vary by project.",
            ]
            if issue_cap:
                notes.append(
                    "Open work was capped at 500 recently updated items; older backlog and stale counts may be understated."
                )
            if commit_cap:
                notes.append("Contributor metrics sample at most 500 recent commits.")
            if not counts:
                notes.append(
                    "No linked human commit authors observed; contributor concentration is unknown."
                )
            if not release:
                notes.append("No published release found; release cadence was not scored.")
            return RepositorySnapshot(
                full_name=canonical,
                description=metadata.get("description") or "",
                stars=metadata["stargazers_count"],
                open_issues=len(tracked_issues),
                open_pull_requests=len(prs),
                stale_issues=stale(tracked_issues),
                stale_pull_requests=stale(prs),
                contributors_last_90_days=len(counts) if counts else None,
                top_contributor_share=max(counts.values()) / sum(counts.values())
                if counts
                else None,
                last_release_days=max(
                    0,
                    (
                        now - datetime.fromisoformat(release["published_at"].replace("Z", "+00:00"))
                    ).days,
                )
                if release
                else None,
                captured_at=now,
                source="github",
                coverage_notes=notes,
                work_items=[
                    WorkItem(
                        number=item["number"],
                        title=item["title"],
                        kind="pull_request" if "pull_request" in item else "issue",
                        updated_at=item["updated_at"],
                    )
                    for item in issues
                ],
            )
        except httpx.HTTPError as error:
            raise ImportFailure(
                "Could not reach GitHub. Check the connection and retry."
            ) from error
        except (KeyError, ValueError, TypeError) as error:
            raise ImportFailure("GitHub returned an unexpected data format.") from error
        finally:
            self.client.close()
