# AI Workflow Observatory Product Roadmap

## Product Positioning

AI Workflow Observatory is a local-first observability layer for AI-assisted engineering workflows.

It answers a different question than a token counter:

```text
Did the AI-assisted engineering workflow behave like a controlled engineering process?
```

The product reconstructs sessions into phases:

- context gathering
- planning
- implementation
- verification
- failure recovery
- final handoff

Then it scores the workflow for verification quality, iteration behavior, and risk.

## v0.1 - Minimal Working Product

Status: done.

- Codex JSONL parser
- deterministic workflow classification
- CLI dashboard
- session trace view
- Markdown and JSON export
- FastAPI web dashboard

## v0.2 - Strong MVP

Status: in progress.

- SQLite-backed local cache
- better function call and tool output correlation
- dashboard filters by project, risk, and verification quality
- clearer workflow trace cards
- privacy-first local data boundary

## v0.3 - Portfolio-Grade Product

Goal: make the project impressive enough to show as a serious AI engineering observability tool.

- stronger Codex parser coverage
- Claude Code session parser
- Cursor session parser
- Git correlation: changed files, diff size, commit links
- workflow quality score
- risky session detector
- HTML report export
- screenshot-ready product README

## v0.4 - Developer Workstation

Goal: make it useful for repeated daily use.

- Textual interactive terminal UI
- SQLite incremental scanner
- file watcher for new sessions
- saved filters
- project drilldown
- session comparison
- configurable policy rules:
  - edits require verification
  - failures require recovery
  - high-risk sessions require human review

## v0.5 - Agent Observability Layer

Goal: turn the tool into infrastructure other agents can use.

- MCP server:
  - `analyze_recent_sessions`
  - `find_unverified_ai_changes`
  - `project_workflow_report`
  - `explain_session_trace`
- optional LLM-generated summaries
- local-only mode by default
- explicit opt-in for hosted model summaries

## v1.0 - Self-Hosted Team Product

Goal: local-first or self-hosted observability for teams using AI coding agents.

- multi-user workspace support
- project-level dashboards
- PR workflow reports
- GitHub Action integration
- policy packs for engineering teams
- privacy controls and redaction
- exportable audit artifacts

## Design Principles

- Local-first by default.
- Raw prompts should not leave the machine unless explicitly enabled.
- Deterministic heuristics first, LLM summaries second.
- Workflow evidence should be visible and inspectable.
- The product should help developers improve engineering behavior, not just track usage.
