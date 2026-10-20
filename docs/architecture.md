# Architecture

```text
Browser dashboard ─┐
                  ├─ FastAPI / validated Pydantic models ─ SQLite
CLI ──────────────┘                │                       ├─ snapshots
                                   └─ GitHubAdapter         ├─ action states
                                          │                └─ capture policies
                                   public GitHub REST API
```

## Boundaries

`github.py` owns HTTP ingestion and error normalization. It uses a fixed `api.github.com` origin, no redirects, request timeouts, and at most five pages per collection. Import requests contain a validated owner/name pair, never an arbitrary URL or credential. The adapter closes its HTTP client after every capture. Authentication, when configured, stays on the server.

`models.py` rejects negative counts, invalid names, naive timestamps, unexpected fields, and stale counts exceeding open counts. Unknown metrics use null. `scoring.py` is a deterministic function: its report is reproducible from any saved snapshot.

`storage.py` uses short-lived SQLite connections with WAL journaling, transactions, parameterized SQL, and a repository/time index. Canonical UTC timestamps govern latest-snapshot selection even when older snapshots arrive later. A SHA-256 digest deduplicates exact repeated payloads. History is append-only; action states are separate from measured data.

`TriagePolicy` is embedded in each snapshot and optionally stored as a repository's next-capture settings. Old payloads default to the original policy. History IDs are the stored digests, not newly computed hashes of deserialized payloads with additional default fields. Comparisons are scoped to a repository and chronological captures. Unknown values keep null deltas; missing sampled items are never described as closed. Policy/source differences produce explicit caveats. Item differences are unavailable when either capture lacks item-level evidence.

`main.py` is an app factory, making the database, demo seeding, write token, and GitHub adapter injectable in tests. The module-level `app` supports Uvicorn. `static/` is included in wheels, and filesystem paths resolve relative to the package rather than the launch directory.

## HTTP contract

| Endpoint | Behavior |
| --- | --- |
| `GET /api/status` | Version, readiness and write-token requirement |
| `GET /api/repositories` | Latest snapshot, report, action states and next-capture policy |
| `GET /api/repositories/{owner}/{name}/health` | Latest explainable report |
| `GET /api/repositories/{owner}/{name}/history` | Chronological snapshots with stable IDs; limit 1–200 |
| `GET/PUT /api/repositories/{owner}/{name}/policy` | Read/update future-capture settings; existing repository required |
| `GET /api/repositories/{owner}/{name}/compare?before=ID&after=ID` | Metric, score and sampled-item differences with coverage caveats |
| `POST /api/import/github` | Capture and persist a public repository |
| `POST /api/repositories/snapshot` | Import a validated manual snapshot |
| `PUT /api/repositories/{owner}/{name}/actions/{category}` | Set open, done or dismissed state and optional note |
| `GET /api/export.csv` | Current portfolio report |

Imports, policy changes and actions require `X-Write-Token` when `WRITE_TOKEN` is configured. Error responses do not include credentials or upstream response bodies. The UI escapes imported text and uses a restrictive content security policy. No GitHub issues, comments, or labels are changed.

## Design tradeoffs

SQLite and one shared workspace make personal installation simple. This release deliberately avoids a background scheduler, accounts, and an event queue. It is appropriate for small portfolios, not an organization-wide analytics service. Large repositories produce explicitly sampled results. Action states describe the user's workflow; they are not inferred from the next capture.

Back up the SQLite database while the app is stopped, or use SQLite's online backup API. Do not copy only the main file while WAL writes are active. Keep credentials and database files out of version control.
