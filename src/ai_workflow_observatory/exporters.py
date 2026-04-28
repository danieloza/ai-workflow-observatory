from __future__ import annotations

import json

from .analysis import activity_breakdown, project_summary
from .models import ObservatoryReport


def export_json(report: ObservatoryReport) -> str:
    return report.model_dump_json(indent=2)


def export_markdown(report: ObservatoryReport) -> str:
    lines = [
        "# AI Workflow Observatory Report",
        "",
        f"Generated: `{report.generated_at.isoformat()}`",
        "",
        "## Overview",
        "",
        f"- Sessions: `{len(report.sessions)}`",
        f"- Iterations: `{sum(session.iterations for session in report.sessions)}`",
        f"- Verified sessions: `{sum(1 for session in report.sessions if session.has_tests)}`",
        f"- Final without verification: `{sum(1 for session in report.sessions if session.final_without_verification)}`",
        f"- Estimated cost USD: `${sum(session.cost.usd for session in report.sessions):.4f}`",
        f"- Estimated cost EUR: `EUR {sum(session.cost.eur for session in report.sessions):.4f}`",
        f"- Estimated cost PLN: `PLN {sum(session.cost.pln for session in report.sessions):.4f}`",
        "",
        "## Projects",
        "",
        "| Project | Sessions | Iterations | USD | Verified | Unverified | Risk |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in project_summary(report):
        project_cost = sum(session.cost.usd for session in report.sessions if session.project == row["project"])
        lines.append(
            f"| {row['project']} | {row['sessions']} | {row['iterations']} | "
            f"{project_cost:.4f} | {row['verified']} | {row['unverified']} | {row['risk']} |"
        )

    lines.extend(["", "## Activity Breakdown", ""])
    for activity, count in activity_breakdown(report).most_common():
        lines.append(f"- `{activity}`: {count}")

    lines.extend(["", "## Recent Sessions", ""])
    for session in report.sessions[:20]:
        started = session.started_at.isoformat() if session.started_at else "unknown"
        lines.extend(
            [
                f"### {session.project} / {started}",
                "",
                f"- Pattern: `{session.pattern}`",
                f"- Iterations: `{session.iterations}`",
                f"- Verification: `{session.verification_quality}`",
                f"- Risk: `{session.risk}`",
                f"- Cost: `${session.cost.usd:.4f}` / `EUR {session.cost.eur:.4f}` / `PLN {session.cost.pln:.4f}`",
                f"- Tokens: `{session.cost.total_tokens}` ({session.cost.pricing_note})",
                "",
            ]
        )
    return "\n".join(lines)


def export_compact_json(report: ObservatoryReport) -> str:
    payload = {
        "generated_at": report.generated_at.isoformat(),
        "projects": project_summary(report),
        "activity": dict(activity_breakdown(report)),
        "sessions": [
            {
                "session_id": session.session_id,
                "project": session.project,
                "started_at": session.started_at.isoformat() if session.started_at else None,
                "pattern": session.pattern,
                "iterations": session.iterations,
                "verification_quality": session.verification_quality,
                "risk": session.risk,
                "cost": session.cost.model_dump(),
            }
            for session in report.sessions
        ],
    }
    return json.dumps(payload, indent=2)
