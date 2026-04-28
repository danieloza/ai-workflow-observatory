from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class EventKind(StrEnum):
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    FILE_READ = "file_read"
    SEARCH = "search"
    EDIT = "edit"
    TEST = "test"
    BUILD = "build"
    GIT = "git"
    ERROR = "error"
    FINAL = "final"
    OTHER = "other"


class WorkflowPhase(StrEnum):
    EXPLORATION = "exploration"
    PLANNING = "planning"
    IMPLEMENTATION = "implementation"
    VERIFICATION = "verification"
    DEBUGGING = "debugging"
    HANDOFF = "handoff"
    OTHER = "other"


class SessionEvent(BaseModel):
    timestamp: datetime | None = None
    kind: EventKind = EventKind.OTHER
    phase: WorkflowPhase = WorkflowPhase.OTHER
    source_type: str | None = None
    label: str
    text: str = ""
    tool_name: str | None = None
    command: str | None = None


class SessionTrace(BaseModel):
    session_id: str
    path: Path
    cwd: str | None = None
    project: str = "unknown"
    started_at: datetime | None = None
    events: list[SessionEvent] = Field(default_factory=list)
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    token_estimate: bool = True


class CostBreakdown(BaseModel):
    model: str = "unknown"
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0
    usd: float = 0.0
    eur: float = 0.0
    pln: float = 0.0
    token_estimate: bool = True
    pricing_note: str = "estimated from session text volume"


class IterationStep(BaseModel):
    phase: WorkflowPhase
    title: str
    event_count: int
    evidence: list[str] = Field(default_factory=list)


class SessionAssessment(BaseModel):
    session_id: str
    project: str
    started_at: datetime | None = None
    event_count: int
    iterations: int
    exploration_before_edit: bool
    has_edits: bool
    has_tests: bool
    has_failures: bool
    recovered_after_failure: bool
    final_without_verification: bool
    verification_quality: str
    risk: str
    pattern: str
    phases: list[IterationStep]
    cost: CostBreakdown = Field(default_factory=CostBreakdown)


class ObservatoryReport(BaseModel):
    generated_at: datetime
    sessions: list[SessionAssessment]
