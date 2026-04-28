from __future__ import annotations

from collections import Counter

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .analysis import activity_breakdown, project_summary
from .models import ObservatoryReport, SessionAssessment


def render_dashboard(report: ObservatoryReport, console: Console | None = None) -> None:
    console = console or Console()
    sessions = report.sessions
    verified = sum(1 for session in sessions if session.has_tests)
    unverified = sum(1 for session in sessions if session.final_without_verification)
    risky = sum(1 for session in sessions if session.risk in {"medium", "high"})
    iterations = sum(session.iterations for session in sessions)

    console.print(_header())
    console.print(
        Panel(
            f"[bold]Sessions[/bold] {len(sessions)}    "
            f"[bold]Iterations[/bold] {iterations}    "
            f"[bold green]Verified[/bold green] {verified}    "
            f"[bold yellow]Unverified[/bold yellow] {unverified}    "
            f"[bold red]Risky[/bold red] {risky}",
            title="Overview",
            border_style="cyan",
            box=box.ROUNDED,
        )
    )
    console.print(_project_table(report))
    console.print(_activity_table(activity_breakdown(report)))
    console.print(_session_table(sessions[:12]))


def render_trace(assessment: SessionAssessment, console: Console | None = None) -> None:
    console = console or Console()
    console.print(_header("Session Trace"))
    console.print(
        Panel(
            f"[bold]Project[/bold] {assessment.project}\n"
            f"[bold]Session[/bold] {assessment.session_id}\n"
            f"[bold]Pattern[/bold] {assessment.pattern}\n"
            f"[bold]Verification[/bold] {assessment.verification_quality}\n"
            f"[bold]Risk[/bold] {_risk_text(assessment.risk)}",
            title="Assessment",
            border_style=_risk_color(assessment.risk),
            box=box.ROUNDED,
        )
    )

    table = Table(title="Workflow Trace", box=box.SIMPLE_HEAVY)
    table.add_column("Phase", style="bold")
    table.add_column("Events", justify="right")
    table.add_column("Evidence")
    for step in assessment.phases:
        table.add_row(step.phase.value, str(step.event_count), ", ".join(step.evidence))
    console.print(table)


def _header(title: str = "AI Workflow Observatory") -> Panel:
    return Panel(
        Text(title, style="bold white"),
        subtitle="local-first workflow trace analysis",
        border_style="bright_blue",
        box=box.DOUBLE,
    )


def _project_table(report: ObservatoryReport) -> Table:
    table = Table(title="Top Projects", box=box.SIMPLE_HEAVY)
    table.add_column("Project", style="bold")
    table.add_column("Sessions", justify="right")
    table.add_column("Iterations", justify="right")
    table.add_column("Verified", justify="right")
    table.add_column("Unverified", justify="right")
    table.add_column("Risk")
    for row in project_summary(report)[:10]:
        risk = str(row["risk"])
        table.add_row(
            str(row["project"]),
            str(row["sessions"]),
            str(row["iterations"]),
            str(row["verified"]),
            str(row["unverified"]),
            _risk_text(risk),
        )
    return table


def _activity_table(counter: Counter[str]) -> Table:
    table = Table(title="Activity Breakdown", box=box.SIMPLE_HEAVY)
    table.add_column("Activity", style="bold")
    table.add_column("Events", justify="right")
    table.add_column("Share")
    total = sum(counter.values()) or 1
    for activity, count in counter.most_common():
        share = count / total
        bar = "#" * max(1, round(share * 20))
        table.add_row(activity, str(count), f"{bar} {share:.0%}")
    return table


def _session_table(sessions: list[SessionAssessment]) -> Table:
    table = Table(title="Recent Sessions", box=box.SIMPLE_HEAVY)
    table.add_column("Started")
    table.add_column("Project")
    table.add_column("Pattern")
    table.add_column("Iter", justify="right")
    table.add_column("Verify")
    table.add_column("Risk")
    for session in sessions:
        started = session.started_at.strftime("%Y-%m-%d %H:%M") if session.started_at else "unknown"
        table.add_row(
            started,
            session.project,
            session.pattern,
            str(session.iterations),
            session.verification_quality,
            _risk_text(session.risk),
        )
    return table


def _risk_text(risk: str) -> str:
    return f"[{_risk_color(risk)}]{risk}[/{_risk_color(risk)}]"


def _risk_color(risk: str) -> str:
    return {"low": "green", "medium": "yellow", "high": "red"}.get(risk, "white")
