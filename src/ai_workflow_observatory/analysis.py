from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone

from .costs import estimate_cost
from .models import (
    EventKind,
    IterationStep,
    ObservatoryReport,
    SessionAssessment,
    SessionEvent,
    SessionTrace,
    WorkflowPhase,
)


def analyze_sessions(sessions: list[SessionTrace]) -> ObservatoryReport:
    return ObservatoryReport(
        generated_at=datetime.now(timezone.utc),
        sessions=[analyze_session(session) for session in sessions],
    )


def analyze_session(session: SessionTrace) -> SessionAssessment:
    events = session.events
    kinds = [event.kind for event in events]
    phases = [event.phase for event in events]

    first_edit = _first_index(kinds, EventKind.EDIT)
    first_exploration = _first_phase_index(phases, WorkflowPhase.EXPLORATION)
    first_failure = _first_index(kinds, EventKind.ERROR)
    last_test = _last_index(kinds, EventKind.TEST)
    last_edit = _last_index(kinds, EventKind.EDIT)

    has_edits = EventKind.EDIT in kinds
    has_tests = EventKind.TEST in kinds
    has_failures = EventKind.ERROR in kinds
    exploration_before_edit = (
        has_edits
        and first_exploration is not None
        and first_edit is not None
        and first_exploration < first_edit
    )
    recovered_after_failure = (
        has_failures
        and first_failure is not None
        and last_test is not None
        and last_test > first_failure
    )
    final_without_verification = has_edits and (not has_tests or (last_edit is not None and last_test is not None and last_edit > last_test))
    iterations = _count_iterations(events)

    verification_quality = _verification_quality(
        has_edits=has_edits,
        has_tests=has_tests,
        has_failures=has_failures,
        recovered_after_failure=recovered_after_failure,
        final_without_verification=final_without_verification,
    )
    risk = _risk_level(
        iterations=iterations,
        has_edits=has_edits,
        has_tests=has_tests,
        has_failures=has_failures,
        exploration_before_edit=exploration_before_edit,
        recovered_after_failure=recovered_after_failure,
        final_without_verification=final_without_verification,
    )

    return SessionAssessment(
        session_id=session.session_id,
        project=session.project,
        started_at=session.started_at,
        event_count=len(events),
        iterations=iterations,
        exploration_before_edit=exploration_before_edit,
        has_edits=has_edits,
        has_tests=has_tests,
        has_failures=has_failures,
        recovered_after_failure=recovered_after_failure,
        final_without_verification=final_without_verification,
        verification_quality=verification_quality,
        risk=risk,
        pattern=_pattern_name(has_edits, has_tests, has_failures, recovered_after_failure),
        phases=_phase_steps(events),
        cost=estimate_cost(session),
    )


def project_summary(report: ObservatoryReport) -> list[dict[str, object]]:
    grouped: dict[str, list[SessionAssessment]] = defaultdict(list)
    for assessment in report.sessions:
        grouped[assessment.project].append(assessment)

    rows: list[dict[str, object]] = []
    for project, sessions in grouped.items():
        risk_counts = Counter(session.risk for session in sessions)
        rows.append(
            {
                "project": project,
                "sessions": len(sessions),
                "iterations": sum(session.iterations for session in sessions),
                "verified": sum(1 for session in sessions if session.has_tests),
                "unverified": sum(1 for session in sessions if session.final_without_verification),
                "risk": _dominant_risk(risk_counts),
            }
        )
    return sorted(rows, key=lambda row: (row["sessions"], row["iterations"]), reverse=True)


def activity_breakdown(report: ObservatoryReport) -> Counter[str]:
    counter: Counter[str] = Counter()
    for session in report.sessions:
        for step in session.phases:
            counter[step.phase.value] += step.event_count
    return counter


def _count_iterations(events: list[SessionEvent]) -> int:
    iterations = 0
    awaiting_fix = False
    for event in events:
        if event.kind == EventKind.ERROR:
            awaiting_fix = True
        elif awaiting_fix and event.kind == EventKind.EDIT:
            iterations += 1
            awaiting_fix = False
        elif event.kind == EventKind.TEST:
            iterations += 1
    if iterations == 0 and any(event.kind == EventKind.EDIT for event in events):
        return 1
    return iterations


def _phase_steps(events: list[SessionEvent]) -> list[IterationStep]:
    grouped: dict[WorkflowPhase, list[SessionEvent]] = defaultdict(list)
    for event in events:
        grouped[event.phase].append(event)

    order = [
        WorkflowPhase.EXPLORATION,
        WorkflowPhase.PLANNING,
        WorkflowPhase.IMPLEMENTATION,
        WorkflowPhase.VERIFICATION,
        WorkflowPhase.DEBUGGING,
        WorkflowPhase.HANDOFF,
        WorkflowPhase.OTHER,
    ]
    steps: list[IterationStep] = []
    for phase in order:
        phase_events = grouped.get(phase, [])
        if not phase_events:
            continue
        evidence = [event.label for event in phase_events[:4]]
        steps.append(
            IterationStep(
                phase=phase,
                title=_phase_title(phase),
                event_count=len(phase_events),
                evidence=evidence,
            )
        )
    return steps


def _verification_quality(
    *,
    has_edits: bool,
    has_tests: bool,
    has_failures: bool,
    recovered_after_failure: bool,
    final_without_verification: bool,
) -> str:
    if not has_edits:
        return "read-only"
    if has_tests and not has_failures and not final_without_verification:
        return "good"
    if has_failures and recovered_after_failure and not final_without_verification:
        return "recovered"
    if has_tests:
        return "mixed"
    return "weak"


def _risk_level(
    *,
    iterations: int,
    has_edits: bool,
    has_tests: bool,
    has_failures: bool,
    exploration_before_edit: bool,
    recovered_after_failure: bool,
    final_without_verification: bool,
) -> str:
    if not has_edits:
        return "low"
    score = 0
    if not exploration_before_edit:
        score += 1
    if not has_tests:
        score += 2
    if final_without_verification:
        score += 2
    if has_failures and not recovered_after_failure:
        score += 2
    if iterations >= 5:
        score += 1
    if score >= 4:
        return "high"
    if score >= 2:
        return "medium"
    return "low"


def _pattern_name(has_edits: bool, has_tests: bool, has_failures: bool, recovered_after_failure: bool) -> str:
    if not has_edits:
        return "exploration-or-conversation"
    if has_failures and recovered_after_failure:
        return "debugging-loop-with-recovery"
    if has_failures:
        return "debugging-loop-unresolved"
    if has_tests:
        return "code-change-with-test"
    return "code-change-without-test"


def _dominant_risk(risk_counts: Counter[str]) -> str:
    for risk in ("high", "medium", "low"):
        if risk_counts[risk]:
            return risk
    return "unknown"


def _phase_title(phase: WorkflowPhase) -> str:
    return {
        WorkflowPhase.EXPLORATION: "Context gathering",
        WorkflowPhase.PLANNING: "Planning",
        WorkflowPhase.IMPLEMENTATION: "Implementation",
        WorkflowPhase.VERIFICATION: "Verification",
        WorkflowPhase.DEBUGGING: "Failure recovery",
        WorkflowPhase.HANDOFF: "Final handoff",
        WorkflowPhase.OTHER: "Other activity",
    }[phase]


def _first_index(items: list[EventKind], target: EventKind) -> int | None:
    try:
        return items.index(target)
    except ValueError:
        return None


def _first_phase_index(items: list[WorkflowPhase], target: WorkflowPhase) -> int | None:
    try:
        return items.index(target)
    except ValueError:
        return None


def _last_index(items: list[EventKind], target: EventKind) -> int | None:
    for index in range(len(items) - 1, -1, -1):
        if items[index] == target:
            return index
    return None
