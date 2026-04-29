from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from .analysis import activity_breakdown, project_summary
from .costs import USD_TO_EUR, USD_TO_PLN
from .storage import cached_projects, load_cached_report, sync_cache
from .web_template import HTML as WEB_HTML

app = FastAPI(title="AI Workflow Observatory")


@app.get("/api/summary")
def api_summary(
    limit: int = Query(25, ge=1, le=200),
    project: str = "all",
    risk: str = "all",
    verification: str = "all",
):
    sync_cache(limit=limit)
    report = load_cached_report(limit=limit, project=project, risk=risk, verification=verification)
    overview = _overview(report)
    return {
        "generated_at": report.generated_at.isoformat(),
        "overview": overview,
        "insights": _insights(report, overview),
        "projects": _project_rows_with_cost(report),
        "project_options": cached_projects(),
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
                "phases": [
                    {
                        "phase": step.phase.value,
                        "title": step.title,
                        "event_count": step.event_count,
                        "evidence": step.evidence,
                    }
                    for step in session.phases
                ],
            }
            for session in report.sessions
        ],
    }


def _overview(report):
    sessions = report.sessions
    session_count = len(sessions)
    iterations = sum(session.iterations for session in sessions)
    verified = sum(1 for session in sessions if session.has_tests)
    unverified = sum(1 for session in sessions if session.final_without_verification)
    risky = sum(1 for session in sessions if session.risk in {"medium", "high"})
    recovered = sum(1 for session in sessions if session.verification_quality == "recovered")
    cost_usd = round(sum(session.cost.usd for session in sessions), 4)
    quality_score = _quality_score(session_count, verified, unverified, risky, recovered)
    return {
        "sessions": session_count,
        "iterations": iterations,
        "verified": verified,
        "unverified": unverified,
        "risky": risky,
        "recovered": recovered,
        "quality_score": quality_score,
        "cost_usd": cost_usd,
        "cost_eur": round(sum(session.cost.eur for session in sessions), 4),
        "cost_pln": round(sum(session.cost.pln for session in sessions), 4),
        "cost_per_session_usd": round(cost_usd / session_count, 4) if session_count else 0,
        "cost_per_iteration_usd": round(cost_usd / iterations, 4) if iterations else 0,
        "cost_estimated": any(session.cost.token_estimate for session in sessions),
    }


def _quality_score(session_count: int, verified: int, unverified: int, risky: int, recovered: int) -> int:
    if session_count == 0:
        return 0
    score = 68
    score += round((verified / session_count) * 22)
    score += round((recovered / session_count) * 6)
    score -= round((unverified / session_count) * 25)
    score -= round((risky / session_count) * 20)
    return max(0, min(100, score))


def _insights(report, overview):
    sessions = report.sessions
    insights = []
    if overview["quality_score"] >= 85:
        insights.append({"level": "good", "title": "Workflow quality is strong", "body": "Most sessions show verification or controlled recovery patterns."})
    elif overview["quality_score"] >= 65:
        insights.append({"level": "warn", "title": "Workflow quality is acceptable", "body": "The workflow is usable, but more sessions should end with explicit verification."})
    else:
        insights.append({"level": "risk", "title": "Workflow quality needs attention", "body": "Too many sessions are unverified or risky for a production engineering loop."})

    if overview["cost_estimated"]:
        insights.append({"level": "info", "title": "Cost is estimated", "body": "No exact token usage was found in these session logs, so costs are estimated from session text volume."})

    expensive = sorted(sessions, key=lambda session: session.cost.usd, reverse=True)[:1]
    if expensive and expensive[0].cost.usd > 0:
        insights.append({"level": "info", "title": "Most expensive session", "body": f"{expensive[0].project} used about ${expensive[0].cost.usd:.2f} with {expensive[0].iterations} iterations."})

    unverified = [session for session in sessions if session.final_without_verification]
    if unverified:
        insights.append({"level": "risk", "title": "Unverified changes detected", "body": f"{len(unverified)} sessions appear to end after edits without a later verification step."})

    return insights[:4]


def _project_rows_with_cost(report):
    rows = project_summary(report)
    cost_by_project = {}
    quality_by_project = {}
    for session in report.sessions:
        cost_by_project.setdefault(session.project, 0.0)
        cost_by_project[session.project] += session.cost.usd
        quality_by_project.setdefault(session.project, []).append(session)
    for row in rows:
        usd = round(cost_by_project.get(str(row["project"]), 0.0), 4)
        sessions = quality_by_project.get(str(row["project"]), [])
        session_count = len(sessions)
        verified = sum(1 for session in sessions if session.has_tests)
        unverified = sum(1 for session in sessions if session.final_without_verification)
        risky = sum(1 for session in sessions if session.risk in {"medium", "high"})
        recovered = sum(1 for session in sessions if session.verification_quality == "recovered")
        row["cost_usd"] = usd
        row["cost_eur"] = round(usd * USD_TO_EUR, 4)
        row["cost_pln"] = round(usd * USD_TO_PLN, 4)
        row["quality_score"] = _quality_score(session_count, verified, unverified, risky, recovered)
    return rows


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return WEB_HTML


