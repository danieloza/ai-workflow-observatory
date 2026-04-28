from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from .analysis import activity_breakdown, project_summary
from .costs import USD_TO_EUR, USD_TO_PLN
from .storage import cached_projects, load_cached_report, sync_cache

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
    return HTML


HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI Workflow Observatory</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #090b0f;
      --surface: #0f141b;
      --surface-2: #141b24;
      --surface-3: #0b1016;
      --line: #273241;
      --line-soft: #1a2430;
      --text: #edf2f7;
      --muted: #97a6b8;
      --muted-2: #6d7b8d;
      --blue: #60a5fa;
      --green: #7ddc9a;
      --yellow: #e7c461;
      --red: #f47777;
      --cyan: #77dce3;
      --violet: #b69cff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 13px/1.45 Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif;
    }
    header {
      border-bottom: 1px solid var(--line);
      padding: 14px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      background: rgba(9, 11, 15, .96);
      position: sticky;
      top: 0;
      z-index: 10;
      backdrop-filter: blur(10px);
    }
    h1 { margin: 0; font-size: 17px; letter-spacing: 0; display: flex; gap: 10px; align-items: center; }
    .subtitle { color: var(--muted); margin-top: 2px; font-size: 12px; }
    .product-mark {
      width: 10px;
      height: 10px;
      background: var(--cyan);
      border-radius: 2px;
      display: inline-block;
      box-shadow: 0 0 18px rgba(118, 227, 234, .5);
    }
    .controls { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }
    input, select {
      background: var(--surface);
      border: 1px solid var(--line);
      color: var(--text);
      padding: 8px 9px;
      border-radius: 6px;
      outline: none;
    }
    input { width: 76px; }
    select { min-width: 132px; }
    button {
      background: var(--blue);
      color: #05111f;
      border: 0;
      border-radius: 6px;
      padding: 9px 13px;
      font-weight: 700;
      cursor: pointer;
    }
    main { padding: 18px 24px 28px; max-width: 1560px; margin: 0 auto; }
    .hero {
      display: grid;
      grid-template-columns: minmax(260px, .9fr) minmax(360px, 1.1fr);
      gap: 14px;
      align-items: stretch;
    }
    .score-card {
      min-height: 214px;
      display: grid;
      grid-template-columns: 144px 1fr;
      gap: 16px;
      align-items: center;
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      min-width: 0;
      box-shadow: 0 10px 28px rgba(0, 0, 0, .18);
    }
    .score-ring {
      width: 132px;
      height: 132px;
      border-radius: 50%;
      display: grid;
      place-items: center;
      background: conic-gradient(var(--green) calc(var(--score) * 1%), #182331 0);
      position: relative;
    }
    .score-ring::after {
      content: "";
      position: absolute;
      inset: 10px;
      border-radius: 50%;
      background: var(--surface);
      border: 1px solid var(--line-soft);
    }
    .score-value {
      position: relative;
      z-index: 1;
      font-size: 34px;
      font-weight: 850;
    }
    .score-label {
      color: var(--muted);
      text-transform: uppercase;
      font-size: 11px;
      letter-spacing: .04em;
    }
    .grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
    .metric-label { color: var(--muted); font-size: 12px; text-transform: uppercase; }
    .metric-value { font-size: 27px; font-weight: 820; margin-top: 4px; letter-spacing: 0; }
    .metric-note { color: var(--muted-2); font-size: 11px; margin-top: 4px; min-height: 16px; }
    [data-tip] { cursor: help; }
    [data-tip]:focus-visible {
      outline: 2px solid var(--cyan);
      outline-offset: 2px;
    }
    #tooltip {
      position: fixed;
      width: min(290px, 72vw);
      background: #f6f8fb;
      color: #111820;
      border: 1px solid #d8e1ea;
      border-radius: 8px;
      padding: 10px 11px;
      box-shadow: 0 18px 44px rgba(0, 0, 0, .42);
      font-size: 12px;
      line-height: 1.35;
      font-weight: 650;
      opacity: 0;
      pointer-events: none;
      transform: translateY(4px);
      transition: opacity .12s ease, transform .12s ease;
      z-index: 100;
      text-transform: none;
    }
    #tooltip.visible {
      opacity: 1;
      transform: translateY(0);
    }
    #tooltip.pinned::before {
      content: "Pinned";
      display: block;
      color: #526170;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: .08em;
      margin-bottom: 4px;
    }
    .help-dot {
      display: inline-grid;
      place-items: center;
      width: 16px;
      height: 16px;
      border: 1px solid var(--line);
      border-radius: 50%;
      color: var(--muted);
      font-size: 11px;
      margin-left: 6px;
      vertical-align: middle;
      background: var(--surface-3);
    }
    .layout { display: grid; grid-template-columns: 1.12fr .88fr; gap: 14px; margin-top: 14px; align-items: start; }
    .wide-layout { display: grid; grid-template-columns: minmax(620px, 1.18fr) minmax(390px, .82fr); gap: 14px; margin-top: 14px; align-items: start; }
    h2 { margin: 0 0 12px; font-size: 14px; letter-spacing: 0; }
    .section-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
    .section-head h2 { margin: 0; }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 9px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { color: var(--muted); font-size: 12px; text-transform: uppercase; }
    tr.clickable { cursor: pointer; }
    tr.clickable:hover, tr.selected { background: var(--surface-2); }
    .risk-low { color: var(--green); }
    .risk-medium { color: var(--yellow); }
    .risk-high { color: var(--red); }
    .badge {
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      background: var(--surface-3);
      padding: 3px 7px;
      border-radius: 999px;
      font-size: 12px;
      white-space: nowrap;
    }
    .badge.low, .badge.good, .badge.recovered { border-color: rgba(126, 231, 135, .35); color: var(--green); }
    .badge.medium, .badge.mixed { border-color: rgba(242, 204, 96, .4); color: var(--yellow); }
    .badge.high, .badge.weak { border-color: rgba(255, 123, 114, .4); color: var(--red); }
    .badge.read-only { color: var(--muted); }
    .bar-row { display: grid; grid-template-columns: 120px 1fr 56px; gap: 10px; align-items: center; margin: 9px 0; }
    .bar-bg { background: #0a1118; border: 1px solid var(--line); height: 10px; border-radius: 99px; overflow: hidden; }
    .bar { background: var(--cyan); height: 100%; }
    .insights { display: grid; gap: 8px; }
    .insight {
      border: 1px solid var(--line);
      background: var(--surface-3);
      border-radius: 8px;
      padding: 11px 12px;
    }
    .insight-title { font-weight: 800; margin-bottom: 3px; }
    .insight-body { color: var(--muted); font-size: 12px; }
    .insight.good { border-color: rgba(125, 220, 154, .32); }
    .insight.warn { border-color: rgba(231, 196, 97, .34); }
    .insight.risk { border-color: rgba(244, 119, 119, .34); }
    .insight.info { border-color: rgba(119, 220, 227, .28); }
    .trace { display: grid; gap: 8px; }
    .trace-panel { position: sticky; top: 92px; }
    .phase {
      background: var(--surface-2);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 11px;
      position: relative;
    }
    .phase-top { display: flex; justify-content: space-between; gap: 10px; }
    .phase-title { font-weight: 800; }
    .evidence { color: var(--muted); margin-top: 6px; font-size: 12px; }
    .phase-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-top: 10px; }
    .mini-stat { background: var(--surface-3); border: 1px solid var(--line-soft); border-radius: 7px; padding: 8px; }
    .mini-stat div:first-child { color: var(--muted); font-size: 11px; text-transform: uppercase; }
    .mini-stat div:last-child { font-size: 16px; font-weight: 800; margin-top: 2px; }
    .timeline {
      display: grid;
      grid-template-columns: 14px 1fr;
      column-gap: 9px;
      row-gap: 0;
      margin-top: 2px;
    }
    .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--cyan);
      margin-top: 14px;
      box-shadow: 0 0 0 4px rgba(119, 220, 227, .1);
    }
    .rail {
      width: 1px;
      background: var(--line);
      margin: 0 auto;
      min-height: 100%;
    }
    .mono { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
    .empty { color: var(--muted); padding: 18px; border: 1px dashed var(--line); border-radius: 8px; }
    .statusline { color: var(--muted); font-size: 12px; margin-top: 10px; display: flex; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
    .privacy { color: var(--green); }
    .table-wrap { overflow-x: auto; }
    @media (max-width: 980px) {
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .hero, .layout, .wide-layout { grid-template-columns: 1fr; }
      .score-card { grid-template-columns: 1fr; }
      .trace-panel { position: static; }
      header { align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <div id="tooltip" role="tooltip"></div>
  <header>
    <div>
      <h1><span class="product-mark"></span>AI Workflow Observatory</h1>
      <div class="subtitle">Local-first workflow trace analysis for AI-assisted engineering</div>
    </div>
    <div class="controls">
      <select id="project" onchange="loadData()"><option value="all">All projects</option></select>
      <select id="risk" onchange="loadData()">
        <option value="all">All risks</option>
        <option value="low">Low risk</option>
        <option value="medium">Medium risk</option>
        <option value="high">High risk</option>
      </select>
      <select id="verification" onchange="loadData()">
        <option value="all">All verification</option>
        <option value="good">Good</option>
        <option value="recovered">Recovered</option>
        <option value="mixed">Mixed</option>
        <option value="weak">Weak</option>
        <option value="read-only">Read-only</option>
      </select>
      <label for="limit" class="subtitle">sessions</label>
      <input id="limit" type="number" min="1" max="200" value="25" />
      <button onclick="loadData()">Refresh</button>
    </div>
  </header>
  <main>
    <section class="hero">
      <div id="score" class="card score-card"></div>
      <div>
        <section id="metrics" class="grid"></section>
      </div>
    </section>
    <div id="status" class="statusline"></div>
    <section class="layout">
      <div class="card">
        <div class="section-head"><h2>Top Projects</h2><span class="subtitle">cost, verification, quality</span></div>
        <div id="projects"></div>
      </div>
      <div class="card">
        <div class="section-head"><h2>Activity Breakdown</h2><span class="subtitle">phase distribution</span></div>
        <div id="activity"></div>
      </div>
    </section>
    <section class="wide-layout">
      <div class="card">
        <div class="section-head"><h2>Recent Sessions</h2><span class="subtitle">click a row to inspect</span></div>
        <div id="sessions"></div>
      </div>
      <div class="card trace-panel">
        <div class="section-head"><h2>Session Trace</h2><span class="subtitle">workflow evidence</span></div>
        <div id="trace" class="trace"></div>
      </div>
    </section>
  </main>
  <script>
    let current = null;
    let projectOptionsInitialized = false;

    async function loadData() {
      const limit = document.getElementById("limit").value || 25;
      const project = document.getElementById("project").value;
      const risk = document.getElementById("risk").value;
      const verification = document.getElementById("verification").value;
      const params = new URLSearchParams({ limit, project, risk, verification });
      const res = await fetch(`/api/summary?${params.toString()}`);
      current = await res.json();
      renderProjectOptions(current.project_options || []);
      renderScore(current.overview, current.insights || []);
      renderMetrics(current.overview);
      renderProjects(current.projects);
      renderActivity(current.activity);
      renderSessions(current.sessions);
      renderTrace(current.sessions[0]);
      document.getElementById("status").innerHTML = `<span>Cache refreshed locally at ${new Date(current.generated_at).toLocaleString()}.</span><span class="privacy">Raw prompts stay on this machine.</span>`;
    }

    function renderProjectOptions(projects) {
      const select = document.getElementById("project");
      const selected = select.value;
      select.innerHTML = `<option value="all">All projects</option>` + projects.map(p => `<option value="${escapeAttr(p)}">${p}</option>`).join("");
      if ([...select.options].some(o => o.value === selected)) select.value = selected;
      projectOptionsInitialized = true;
    }

    function renderMetrics(overview) {
      const items = [
        ["Sessions", overview.sessions, "loaded from local cache"],
        ["Iterations", overview.iterations, "detected workflow loops"],
        ["Verified", overview.verified, "sessions with test/build/git checks"],
        ["Recovered", overview.recovered, "failures followed by verification"],
        ["Est. USD", money(overview.cost_usd, "$"), `${money(overview.cost_per_session_usd, "$")} / session`],
        ["Est. PLN", money(overview.cost_pln, "PLN "), `${money(overview.cost_per_iteration_usd, "$")} / iteration`],
        ["Unverified", overview.unverified, "edits without later verification"],
        ["Risky", overview.risky, "medium or high risk sessions"],
      ];
      document.getElementById("metrics").innerHTML = items.map(([label, value, note]) => `
        <div class="card" data-tip="${metricTip(label)}">
          <div class="metric-label">${label}</div>
          <div class="metric-value">${value}</div>
          <div class="metric-note">${note}</div>
        </div>
      `).join("");
    }

    function renderScore(overview, insights) {
      const score = Number(overview.quality_score || 0);
      const tone = score >= 85 ? "strong" : score >= 65 ? "watch" : "risk";
      document.getElementById("score").innerHTML = `
        <div class="score-ring" style="--score:${score}" data-tip="A management-friendly score for how controlled the AI workflow looks. Higher means more verification, fewer risky endings, and better failure recovery.">
          <div class="score-value">${score}</div>
        </div>
        <div>
          <div class="score-label">Workflow Quality <span class="help-dot" data-tip="This does not judge whether the model was smart. It judges the engineering process around the AI work: context, verification, recovery and risk.">?</span></div>
          <div class="metric-value">${tone}</div>
          <div class="subtitle">Verification, recovery, risk and handoff quality across the selected sessions.</div>
          <div class="phase-grid">
            <div class="mini-stat" data-tip="Average estimated AI cost for one work session. Useful for budget and procurement conversations."><div>Cost/session</div><div>${money(overview.cost_per_session_usd, "$")}</div></div>
            <div class="mini-stat" data-tip="Estimated AI cost divided by detected workflow iterations. Helps identify expensive retry loops."><div>Cost/iter</div><div>${money(overview.cost_per_iteration_usd, "$")}</div></div>
            <div class="mini-stat" data-tip="Yes means exact billing tokens were not found in the local logs, so the tool estimates cost from session text volume."><div>Estimated</div><div>${overview.cost_estimated ? "yes" : "no"}</div></div>
          </div>
          <div class="insights" style="margin-top:10px">
            ${insights.map(item => `<div class="insight ${item.level}"><div class="insight-title">${item.title}</div><div class="insight-body">${item.body}</div></div>`).join("")}
          </div>
        </div>
      `;
    }

    function renderProjects(projects) {
      if (!projects.length) {
        document.getElementById("projects").innerHTML = `<div class="empty">No projects match the current filters.</div>`;
        return;
      }
      document.getElementById("projects").innerHTML = `
        <div class="table-wrap"><table>
          <thead><tr><th data-tip="Project or normalized workspace source detected from local session metadata.">Project</th><th data-tip="How many AI work sessions belong to this project.">Sessions</th><th data-tip="Detected workflow loops such as testing, failures, fixes and repeated attempts.">Iterations</th><th data-tip="Estimated AI usage cost for this project in US dollars.">USD</th><th data-tip="Workflow discipline score for this project.">Quality</th><th data-tip="Sessions with verification signals such as tests, builds or git checks.">Verified</th><th data-tip="Workflow risk based on missing verification or unresolved failures.">Risk</th></tr></thead>
          <tbody>
            ${projects.map(p => `<tr><td data-tip="${projectTip(p.project)}">${p.project}</td><td>${p.sessions}</td><td>${p.iterations}</td><td>${money(p.cost_usd, "$")}</td><td data-tip="Higher means more verified and controlled AI workflow behavior.">${p.quality_score}</td><td>${p.verified}</td><td>${badge(p.risk)}</td></tr>`).join("")}
          </tbody>
        </table></div>
      `;
    }

    function renderActivity(activity) {
      const entries = Object.entries(activity).sort((a, b) => b[1] - a[1]);
      if (!entries.length) {
        document.getElementById("activity").innerHTML = `<div class="empty">No activity for this filter.</div>`;
        return;
      }
      const total = entries.reduce((sum, [, value]) => sum + value, 0) || 1;
      document.getElementById("activity").innerHTML = entries.map(([name, value]) => {
        const pct = Math.round((value / total) * 100);
        return `<div class="bar-row" data-tip="${activityTip(name)}"><div>${name}</div><div class="bar-bg"><div class="bar" style="width:${pct}%"></div></div><div>${pct}%</div></div>`;
      }).join("");
    }

    function renderSessions(sessions) {
      if (!sessions.length) {
        document.getElementById("sessions").innerHTML = `<div class="empty">No sessions match the current filters.</div>`;
        return;
      }
      document.getElementById("sessions").innerHTML = `
        <div class="table-wrap"><table>
          <thead><tr><th data-tip="When the AI session started.">Started</th><th data-tip="Project or normalized source.">Project</th><th data-tip="Short label describing the workflow shape.">Pattern</th><th data-tip="How many workflow loops were detected.">Iter</th><th data-tip="Estimated cost of this session.">USD</th><th data-tip="Whether verification or recovery was detected.">Verify</th><th data-tip="Workflow risk level.">Risk</th></tr></thead>
          <tbody>
            ${sessions.slice(0, 20).map((s, i) => `
              <tr id="session-row-${i}" class="clickable" onclick="selectSession(${i})">
                <td class="mono">${s.started_at ? s.started_at.slice(0, 16).replace("T", " ") : "unknown"}</td>
                <td>${s.project}</td>
                <td data-tip="${patternTip(s.pattern)}">${s.pattern}</td>
                <td>${s.iterations}</td>
                <td>${money(s.cost.usd, "$")}</td>
                <td>${badge(s.verification_quality)}</td>
                <td>${badge(s.risk)}</td>
              </tr>
            `).join("")}
          </tbody>
        </table></div>
      `;
    }

    function selectSession(index) {
      [...document.querySelectorAll("tr.selected")].forEach(row => row.classList.remove("selected"));
      const row = document.getElementById(`session-row-${index}`);
      if (row) row.classList.add("selected");
      renderTrace(current.sessions[index]);
    }

    function renderTrace(session) {
      if (!session) {
        document.getElementById("trace").innerHTML = "<div class='subtitle'>No session selected.</div>";
        return;
      }
      document.getElementById("trace").innerHTML = `
        <div class="phase" data-tip="Selected session summary: project, risk, cost, tokens and workflow pattern. This is the easiest panel to explain to a manager.">
          <div class="phase-top"><div class="phase-title">${session.project}</div><div>${badge(session.risk)}</div></div>
          <div class="evidence mono">${session.session_id}</div>
          <div class="evidence">Pattern: ${session.pattern} | Iterations: ${session.iterations} | Verification: ${session.verification_quality}</div>
          <div class="evidence">Cost: ${money(session.cost.usd, "$")} / ${money(session.cost.eur, "EUR ")} / ${money(session.cost.pln, "PLN ")} (${session.cost.pricing_note})</div>
          <div class="evidence">Tokens: ${session.cost.total_tokens} total, model: ${session.cost.model}</div>
          <div class="phase-grid">
            <div class="mini-stat" data-tip="Approximate tokens read by the model."><div>Input</div><div>${session.cost.input_tokens}</div></div>
            <div class="mini-stat" data-tip="Approximate tokens generated by the model."><div>Output</div><div>${session.cost.output_tokens}</div></div>
            <div class="mini-stat" data-tip="Input plus output tokens. Exactness depends on local log metadata."><div>Total</div><div>${session.cost.total_tokens}</div></div>
          </div>
        </div>
        <div class="timeline">
          ${session.phases.map(p => `
            <div>
              <div class="dot"></div>
              <div class="rail"></div>
            </div>
            <div class="phase" data-tip="${activityTip(p.phase)}">
              <div class="phase-top"><div class="phase-title">${p.title}</div><div>${p.event_count} events</div></div>
              <div class="evidence">${p.evidence.join(", ")}</div>
            </div>
          `).join("")}
        </div>
      `;
    }

    function badge(value) {
      return `<span class="badge ${String(value).replaceAll(" ", "-")}" data-tip="${badgeTip(value)}">${value}</span>`;
    }

    function escapeAttr(value) {
      return String(value).replaceAll("&", "&amp;").replaceAll('"', "&quot;").replaceAll("<", "&lt;");
    }

    function money(value, prefix) {
      const n = Number(value || 0);
      if (n < 0.01) return `${prefix}${n.toFixed(4)}`;
      if (n < 10) return `${prefix}${n.toFixed(2)}`;
      return `${prefix}${Math.round(n)}`;
    }

    function metricTip(label) {
      const tips = {
        "Sessions": "Number of AI work sessions in this view. One session is usually one conversation or coding run.",
        "Iterations": "Detected loops in the work, for example test, fail, fix and retest. More iterations can mean deeper work or repeated friction.",
        "Verified": "Sessions with a verification signal such as tests, builds, linting or git checks.",
        "Recovered": "Sessions where something failed, but the workflow later appears to recover with verification.",
        "Est. USD": "Estimated AI usage cost in US dollars for the selected sessions.",
        "Est. PLN": "Estimated AI usage cost converted to PLN, useful for local business conversations.",
        "Unverified": "Sessions that appear to change something without a later verification step.",
        "Risky": "Sessions marked medium or high risk by workflow heuristics."
      };
      return tips[label] || "Dashboard metric.";
    }

    function activityTip(name) {
      const tips = {
        "exploration": "The AI was gathering context by reading files, searching, or inspecting the environment.",
        "planning": "The AI was organizing the work before execution.",
        "implementation": "The AI appears to be changing files or applying edits.",
        "verification": "The workflow includes tests, builds, git checks or similar validation.",
        "debugging": "The session contains errors, failures or recovery work.",
        "handoff": "The final explanation or summary at the end of the session.",
        "other": "Events not yet classified. This should shrink as the parser becomes smarter."
      };
      return tips[name] || "Workflow phase detected from local AI session logs.";
    }

    function badgeTip(value) {
      const tips = {
        "low": "Low workflow risk: no obvious unverified or unresolved behavior was detected.",
        "medium": "Medium workflow risk: review may be useful before trusting the output.",
        "high": "High workflow risk: likely missing verification or unresolved failures.",
        "good": "Good verification: the session contains clear validation signals.",
        "recovered": "Recovered: the session had a failure and later showed recovery or verification.",
        "mixed": "Mixed: some verification exists, but there are warning signs.",
        "weak": "Weak: the session lacks strong verification.",
        "read-only": "Read-only: mostly inspection or discussion, without clear code-change behavior."
      };
      return tips[value] || "Status label.";
    }

    function patternTip(pattern) {
      const tips = {
        "exploration-or-conversation": "Mostly analysis, discussion or read-only work. Useful for research, but not strong proof of implementation.",
        "debugging-loop-with-recovery": "The workflow hit a failure and then recovered. This is usually a healthy engineering pattern.",
        "debugging-loop-unresolved": "The workflow hit a failure and no clear recovery was detected.",
        "code-change-with-test": "The session appears to include code changes followed by verification.",
        "code-change-without-test": "The session appears to include code changes without later verification."
      };
      return tips[pattern] || "Detected workflow pattern.";
    }

    function projectTip(project) {
      const tips = {
        "workspace-root": "A session started from the main workspace folder, not one specific repository.",
        "conversation": "A conversation or handoff-style session, not a real project folder.",
        "external-system": "A session started from a system folder outside the normal project workspace."
      };
      return tips[project] || "A project or repository detected from the local session path.";
    }

    const tooltip = document.getElementById("tooltip");
    let pinnedTooltip = false;

    document.addEventListener("mouseover", event => {
      const target = event.target.closest("[data-tip]");
      if (pinnedTooltip || !target) return;
      showTooltip(target, event);
    });
    document.addEventListener("focusin", event => {
      const target = event.target.closest("[data-tip]");
      if (!target) return;
      showTooltip(target, event);
    });
    document.addEventListener("mousemove", event => {
      if (tooltip.classList.contains("visible") && !pinnedTooltip) moveTooltip(event);
    });
    document.addEventListener("mouseout", event => {
      if (!pinnedTooltip && event.target.closest("[data-tip]")) hideTooltip();
    });
    document.addEventListener("focusout", event => {
      if (!pinnedTooltip && event.target.closest("[data-tip]")) hideTooltip();
    });
    document.addEventListener("click", event => {
      const target = event.target.closest("[data-tip]");
      if (!target) {
        pinnedTooltip = false;
        hideTooltip();
        return;
      }
      pinnedTooltip = true;
      showTooltip(target, event);
      tooltip.classList.add("pinned");
      event.stopPropagation();
    });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape") {
        pinnedTooltip = false;
        hideTooltip();
      }
    });

    function showTooltip(target, event) {
      tooltip.textContent = target.getAttribute("data-tip");
      tooltip.classList.add("visible");
      if (!pinnedTooltip) tooltip.classList.remove("pinned");
      moveTooltip(event);
    }

    function hideTooltip() {
      tooltip.classList.remove("visible", "pinned");
    }

    function moveTooltip(event) {
      const padding = 14;
      const width = 290;
      const rect = event.target && event.target.getBoundingClientRect ? event.target.getBoundingClientRect() : null;
      const x = event.clientX || (rect ? rect.left + rect.width / 2 : padding);
      const y = event.clientY || (rect ? rect.bottom : padding);
      let left = x + 14;
      let top = y + 14;
      if (left + width > window.innerWidth - padding) left = x - width - 14;
      if (top + 110 > window.innerHeight - padding) top = y - 124;
      tooltip.style.left = `${Math.max(padding, left)}px`;
      tooltip.style.top = `${Math.max(padding, top)}px`;
    }

    loadData();
  </script>
</body>
</html>
"""
