from __future__ import annotations

import re
from pathlib import Path

from .models import EventKind, WorkflowPhase


READ_TOOLS = {"read_file", "read", "get-content", "cat", "sed", "nl"}
SEARCH_TOOLS = {"rg", "grep", "find", "select-string"}
EDIT_TOOLS = {"apply_patch", "write_file", "edit", "python_script_edit"}
TEST_HINTS = ("pytest", "unittest", "vitest", "jest", "npm test", "ruff", "mypy")
BUILD_HINTS = ("npm run build", "docker build", "docker compose", "uvicorn", "tsc")
GIT_HINTS = ("git status", "git diff", "git show", "git log", "git commit", "git push")
ERROR_HINTS = (
    "traceback",
    "failed",
    "failure",
    "error:",
    "exception",
    "assertionerror",
    "exit code: 1",
    "command failed",
)


def project_name_from_cwd(cwd: str | None) -> str:
    if not cwd:
        return "unknown"
    path = Path(cwd)
    name = path.name
    if not name:
        return "unknown"
    normalized = name.lower()
    if normalized == "projekty":
        return "workspace-root"
    if normalized == "system32":
        return "external-system"
    if _looks_like_conversation_slug(normalized):
        return "conversation"
    if path.exists() and (path / ".git").exists():
        return name
    if path.exists() and "projekty" in [part.lower() for part in path.parts]:
        return name
    if "-" in normalized and not path.exists():
        return "conversation"
    return name


def _looks_like_conversation_slug(name: str) -> bool:
    markers = {
        "poni",
        "ponizej",
        "gotowe",
        "readme",
        "konwersacji",
        "czatu",
        "chat",
        "hej",
    }
    parts = {part for part in re.split(r"[-_\s]+", name) if part}
    if len(parts & markers) >= 2:
        return True
    if name.count("-") >= 4 and ("readme" in parts or "gotowe" in parts):
        return True
    return False


def classify_tool(tool_name: str | None, text: str) -> tuple[EventKind, WorkflowPhase]:
    haystack = f"{tool_name or ''} {text}".lower()
    normalized_tool = (tool_name or "").lower()

    if normalized_tool in EDIT_TOOLS or "apply_patch" in haystack:
        return EventKind.EDIT, WorkflowPhase.IMPLEMENTATION
    if any(hint in haystack for hint in TEST_HINTS):
        return EventKind.TEST, WorkflowPhase.VERIFICATION
    if any(hint in haystack for hint in BUILD_HINTS):
        return EventKind.BUILD, WorkflowPhase.VERIFICATION
    if any(hint in haystack for hint in GIT_HINTS):
        return EventKind.GIT, WorkflowPhase.VERIFICATION
    if normalized_tool in READ_TOOLS or re.search(r"\bget-content\b|\bcat\b", haystack):
        return EventKind.FILE_READ, WorkflowPhase.EXPLORATION
    if normalized_tool in SEARCH_TOOLS or re.search(r"\brg\b|\bgrep\b|select-string", haystack):
        return EventKind.SEARCH, WorkflowPhase.EXPLORATION
    if any(hint in haystack for hint in ERROR_HINTS):
        return EventKind.ERROR, WorkflowPhase.DEBUGGING
    return EventKind.TOOL_CALL, WorkflowPhase.OTHER


def classify_text(role: str | None, text: str) -> tuple[EventKind, WorkflowPhase]:
    lower = text.lower()
    if role == "user":
        return EventKind.USER_MESSAGE, WorkflowPhase.OTHER
    if "plan" in lower or "i'll" in lower or "i will" in lower or "zrobi" in lower:
        return EventKind.ASSISTANT_MESSAGE, WorkflowPhase.PLANNING
    if "done" in lower or "completed" in lower or "gotowe" in lower or "final" in lower:
        return EventKind.FINAL, WorkflowPhase.HANDOFF
    if any(hint in lower for hint in ERROR_HINTS):
        return EventKind.ERROR, WorkflowPhase.DEBUGGING
    return EventKind.ASSISTANT_MESSAGE, WorkflowPhase.OTHER
