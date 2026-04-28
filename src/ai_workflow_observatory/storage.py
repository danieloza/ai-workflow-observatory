from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .analysis import analyze_sessions
from .models import ObservatoryReport, SessionAssessment
from .parser import default_codex_sessions_dir, load_sessions


def default_db_path() -> Path:
    return Path.home() / ".ai-workflow-observatory" / "observatory.sqlite"


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            project TEXT NOT NULL,
            started_at TEXT,
            path TEXT NOT NULL,
            cwd TEXT,
            event_count INTEGER NOT NULL,
            trace_json TEXT NOT NULL,
            assessment_json TEXT NOT NULL,
            scanned_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_sessions_started_at ON sessions(started_at DESC);
        CREATE INDEX IF NOT EXISTS idx_sessions_project ON sessions(project);
        """
    )
    conn.commit()


def sync_cache(
    *,
    root: Path | None = None,
    limit: int | None = 100,
    db_path: Path | None = None,
) -> ObservatoryReport:
    sessions = load_sessions(root=root or default_codex_sessions_dir(), limit=limit)
    report = analyze_sessions(sessions)
    scanned_at = datetime.now(timezone.utc).isoformat()

    with connect(db_path) as conn:
        for trace, assessment in zip(sessions, report.sessions, strict=False):
            conn.execute(
                """
                INSERT INTO sessions (
                    session_id, project, started_at, path, cwd, event_count,
                    trace_json, assessment_json, scanned_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    project=excluded.project,
                    started_at=excluded.started_at,
                    path=excluded.path,
                    cwd=excluded.cwd,
                    event_count=excluded.event_count,
                    trace_json=excluded.trace_json,
                    assessment_json=excluded.assessment_json,
                    scanned_at=excluded.scanned_at
                """,
                (
                    trace.session_id,
                    trace.project,
                    trace.started_at.isoformat() if trace.started_at else None,
                    str(trace.path),
                    trace.cwd,
                    len(trace.events),
                    trace.model_dump_json(),
                    assessment.model_dump_json(),
                    scanned_at,
                ),
            )
        conn.commit()
    return report


def load_cached_report(
    *,
    limit: int = 100,
    db_path: Path | None = None,
    project: str | None = None,
    risk: str | None = None,
    verification: str | None = None,
) -> ObservatoryReport:
    query = "SELECT assessment_json FROM sessions"
    clauses: list[str] = []
    params: list[object] = []

    if project and project != "all":
        clauses.append("project = ?")
        params.append(project)
    if risk and risk != "all":
        clauses.append("json_extract(assessment_json, '$.risk') = ?")
        params.append(risk)
    if verification and verification != "all":
        clauses.append("json_extract(assessment_json, '$.verification_quality') = ?")
        params.append(verification)
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY started_at DESC LIMIT ?"
    params.append(limit)

    with connect(db_path) as conn:
        rows = conn.execute(query, params).fetchall()

    assessments = [SessionAssessment.model_validate(json.loads(row["assessment_json"])) for row in rows]
    return ObservatoryReport(generated_at=datetime.now(timezone.utc), sessions=assessments)


def cached_projects(db_path: Path | None = None) -> list[str]:
    with connect(db_path) as conn:
        rows = conn.execute("SELECT DISTINCT project FROM sessions ORDER BY project").fetchall()
    return [str(row["project"]) for row in rows]
