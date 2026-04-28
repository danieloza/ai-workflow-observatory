from __future__ import annotations

from pathlib import Path

from ai_workflow_observatory.analysis import analyze_session
from ai_workflow_observatory.models import EventKind, SessionEvent, SessionTrace, WorkflowPhase


def test_code_change_with_test_is_low_risk() -> None:
    trace = SessionTrace(
        session_id="s1",
        path=Path("s1.jsonl"),
        project="demo",
        events=[
            SessionEvent(kind=EventKind.SEARCH, phase=WorkflowPhase.EXPLORATION, label="rg"),
            SessionEvent(kind=EventKind.EDIT, phase=WorkflowPhase.IMPLEMENTATION, label="apply_patch"),
            SessionEvent(kind=EventKind.TEST, phase=WorkflowPhase.VERIFICATION, label="pytest"),
        ],
    )

    assessment = analyze_session(trace)

    assert assessment.pattern == "code-change-with-test"
    assert assessment.verification_quality == "good"
    assert assessment.risk == "low"
    assert assessment.exploration_before_edit is True


def test_edit_without_test_is_high_risk_when_no_exploration() -> None:
    trace = SessionTrace(
        session_id="s2",
        path=Path("s2.jsonl"),
        project="demo",
        events=[
            SessionEvent(kind=EventKind.EDIT, phase=WorkflowPhase.IMPLEMENTATION, label="apply_patch"),
        ],
    )

    assessment = analyze_session(trace)

    assert assessment.pattern == "code-change-without-test"
    assert assessment.verification_quality == "weak"
    assert assessment.final_without_verification is True
    assert assessment.risk == "high"


def test_failure_followed_by_edit_and_test_counts_recovery() -> None:
    trace = SessionTrace(
        session_id="s3",
        path=Path("s3.jsonl"),
        project="demo",
        events=[
            SessionEvent(kind=EventKind.SEARCH, phase=WorkflowPhase.EXPLORATION, label="rg"),
            SessionEvent(kind=EventKind.EDIT, phase=WorkflowPhase.IMPLEMENTATION, label="apply_patch"),
            SessionEvent(kind=EventKind.ERROR, phase=WorkflowPhase.DEBUGGING, label="pytest failed"),
            SessionEvent(kind=EventKind.EDIT, phase=WorkflowPhase.IMPLEMENTATION, label="apply_patch"),
            SessionEvent(kind=EventKind.TEST, phase=WorkflowPhase.VERIFICATION, label="pytest"),
        ],
    )

    assessment = analyze_session(trace)

    assert assessment.recovered_after_failure is True
    assert assessment.pattern == "debugging-loop-with-recovery"
    assert assessment.iterations >= 2
