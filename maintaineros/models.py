from datetime import UTC, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

REPO_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9_.-]{1,100}$"
ActionState = Literal["open", "done", "dismissed"]


class WorkItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    number: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=500)
    kind: Literal["issue", "pull_request"]
    updated_at: AwareDatetime


class TriagePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stale_days: int = Field(default=30, ge=1, le=365)
    release_gap_days: int = Field(default=180, ge=1, le=3650)
    concentration_threshold: float = Field(default=0.7, ge=0.5, le=1)
    check_releases: bool = True
    check_concentration: bool = True


class RepositorySnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str = Field(pattern=REPO_PATTERN)
    description: str = Field(default="", max_length=2000)
    stars: int = Field(default=0, ge=0)
    open_issues: int = Field(default=0, ge=0)
    open_pull_requests: int = Field(default=0, ge=0)
    stale_issues: int = Field(default=0, ge=0)
    stale_pull_requests: int = Field(default=0, ge=0)
    contributors_last_90_days: int | None = Field(default=None, ge=0)
    top_contributor_share: float | None = Field(default=None, ge=0, le=1)
    last_release_days: int | None = Field(default=None, ge=0)
    source: Literal["manual", "github", "demo"] = "manual"
    coverage_notes: list[str] = Field(default_factory=list, max_length=20)
    captured_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    work_items: list[WorkItem] = Field(default_factory=list, max_length=500)
    policy: TriagePolicy = Field(default_factory=TriagePolicy)

    @field_validator("full_name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.lower()

    @model_validator(mode="after")
    def counts_are_consistent(self):
        if (
            self.stale_issues > self.open_issues
            or self.stale_pull_requests > self.open_pull_requests
        ):
            raise ValueError("Stale counts cannot exceed open counts")
        return self


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
    source: str
    coverage_notes: list[str]
    policy: TriagePolicy


class GitHubImport(BaseModel):
    full_name: str = Field(pattern=REPO_PATTERN)


class ActionUpdate(BaseModel):
    state: ActionState
    note: str = Field(default="", max_length=1000)
