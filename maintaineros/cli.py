import argparse
import json
import os
import sys

from .github import GitHubAdapter, ImportFailure
from .models import GitHubImport
from .scoring import build_report
from .storage import Store


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Capture GitHub health snapshots or print a local maintainer report."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="Read a public GitHub repository and save a snapshot")
    scan.add_argument("repository", help="owner/repository")
    scan.add_argument("--db", default=os.getenv("MAINTAINEROS_DB", "data/maintaineros.sqlite3"))
    scan.add_argument("--fail-under", type=int, choices=range(0, 101), default=0, metavar="0..100")
    report = sub.add_parser("report", help="Print reports for the latest stored snapshots")
    report.add_argument("--db", default=os.getenv("MAINTAINEROS_DB", "data/maintaineros.sqlite3"))
    report.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            validated = GitHubImport(full_name=args.repository)
            snapshot = GitHubAdapter(os.getenv("GITHUB_TOKEN")).snapshot(validated.full_name)
            Store(args.db).save(snapshot)
            health = build_report(snapshot)
            print(health.model_dump_json(indent=2))
            return 1 if health.score < args.fail_under else 0
        reports = [build_report(s) for s in Store(args.db).latest()]
        if args.format == "json":
            print(json.dumps([r.model_dump(mode="json") for r in reports], indent=2))
        else:
            print("# MaintainerOS report\n")
            for health in reports:
                print(f"## {health.repository} · {health.score}/100 ({health.status})\n")
                for finding in health.findings:
                    print(f"- {finding.title}: {finding.action}")
                for note in health.coverage_notes:
                    print(f"\nCoverage: {note}")
                print()
        return 0
    except (ImportFailure, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
