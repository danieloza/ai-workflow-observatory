from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from .exporters import export_compact_json, export_json, export_markdown
from .parser import default_codex_sessions_dir
from .rendering import render_dashboard, render_trace
from .storage import load_cached_report, sync_cache

app = typer.Typer(
    help="Local observability for AI-assisted engineering workflows.",
    no_args_is_help=False,
)
console = Console()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Codex session file or session directory."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-l", help="Number of newest sessions to scan.")] = 25,
) -> None:
    if ctx.invoked_subcommand is not None:
        return
    report = _build_report(path, limit)
    render_dashboard(report, console)


@app.command()
def summary(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Codex session file or session directory."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-l")] = 25,
) -> None:
    """Render the terminal dashboard."""
    report = _build_report(path, limit)
    render_dashboard(report, console)


@app.command()
def scan(
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Codex session file or session directory."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-l")] = 100,
) -> None:
    """Scan local session logs into the SQLite cache."""
    report = _build_report(path, limit)
    console.print(
        f"[green]Scanned[/green] {len(report.sessions)} sessions, "
        f"{sum(session.iterations for session in report.sessions)} iterations."
    )


@app.command()
def trace(
    index: Annotated[int, typer.Argument(help="Zero-based index from the recent sessions list.")] = 0,
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Codex session file or session directory."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-l")] = 25,
) -> None:
    """Show phase-by-phase analysis for one session."""
    report = _build_report(path, limit)
    if not report.sessions:
        console.print("[red]No sessions found.[/red]")
        raise typer.Exit(1)
    try:
        assessment = report.sessions[index]
    except IndexError:
        console.print(f"[red]Session index {index} not found. Loaded {len(report.sessions)} sessions.[/red]")
        raise typer.Exit(1)
    render_trace(assessment, console)


@app.command("export")
def export_report(
    format_: Annotated[str, typer.Option("--format", "-f", help="markdown, json, or compact-json.")] = "markdown",
    path: Annotated[
        Path | None,
        typer.Option("--path", "-p", help="Codex session file or session directory."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", "-l")] = 25,
    output: Annotated[Path | None, typer.Option("--output", "-o", help="Optional output file.")] = None,
) -> None:
    """Export workflow analysis as Markdown or JSON."""
    report = _build_report(path, limit)
    if format_ == "markdown":
        content = export_markdown(report)
    elif format_ == "json":
        content = export_json(report)
    elif format_ == "compact-json":
        content = export_compact_json(report)
    else:
        console.print("[red]Unsupported format. Use markdown, json, or compact-json.[/red]")
        raise typer.Exit(1)

    if output:
        output.write_text(content, encoding="utf-8")
        console.print(f"[green]Wrote[/green] {output}")
        return
    console.print(content)


def _build_report(path: Path | None, limit: int):
    root = path or default_codex_sessions_dir()
    sync_cache(root=root, limit=limit)
    return load_cached_report(limit=limit)


if __name__ == "__main__":
    app()
