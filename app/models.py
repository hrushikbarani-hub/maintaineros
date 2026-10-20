from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class RepositorySnapshot(BaseModel):
    full_name: str
    description: str = ""
    stars: int = Field(default=0, ge=0)
    open_issues: int = Field(default=0, ge=0)
    open_pull_requests: int = Field(default=0, ge=0)
    stale_issues: int = Field(default=0, ge=0)
    stale_pull_requests: int = Field(default=0, ge=0)
    contributors_last_90_days: int = Field(default=0, ge=0)
    top_contributor_share: float = Field(default=0.0, ge=0.0, le=1.0)
    last_release_days: int | None = Field(default=None, ge=0)
    captured_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Finding(BaseModel):
    severity: Literal["info", "warning", "critical"]
    category: str
    title: str
    detail: str
    action: str


class HealthReport(BaseModel):
    repository: str
    score: int = Field(ge=0, le=100)
    status: Literal["healthy", "watch", "at_risk"]
    findings: list[Finding]
    captured_at: datetime

