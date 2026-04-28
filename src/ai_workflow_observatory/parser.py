from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

from .classifier import classify_text, classify_tool, project_name_from_cwd
from .models import EventKind, SessionEvent, SessionTrace


def default_codex_sessions_dir() -> Path:
    return Path.home() / ".codex" / "sessions"


def iter_session_files(root: Path) -> Iterable[Path]:
    if root.is_file():
        yield root
        return
    if not root.exists():
        return
    yield from sorted(root.rglob("*.jsonl"), key=lambda path: path.stat().st_mtime, reverse=True)


def parse_session_file(path: Path) -> SessionTrace:
    session_id = path.stem
    cwd: str | None = None
    started_at: datetime | None = None
    model: str | None = None
    input_tokens = 0
    output_tokens = 0
    cached_tokens = 0
    token_estimate = True
    events: list[SessionEvent] = []
    calls_by_id: dict[str, tuple[str | None, str | None]] = {}

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            timestamp = _parse_dt(record.get("timestamp"))
            record_type = record.get("type")
            payload = record.get("payload") or {}

            if record_type == "session_meta":
                meta = payload
                session_id = str(meta.get("id") or session_id)
                cwd = meta.get("cwd") or cwd
                model = meta.get("model") or meta.get("model_provider") or model
                started_at = _parse_dt(meta.get("timestamp")) or timestamp or started_at
                continue

            usage = _extract_usage(record)
            if usage:
                input_tokens += usage[0]
                output_tokens += usage[1]
                cached_tokens += usage[2]
                token_estimate = False

            events.extend(_events_from_record(record_type, payload, timestamp, calls_by_id))

    return SessionTrace(
        session_id=session_id,
        path=path,
        cwd=cwd,
        project=project_name_from_cwd(cwd),
        started_at=started_at,
        events=events,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        token_estimate=token_estimate,
    )


def load_sessions(root: Path | None = None, limit: int | None = None) -> list[SessionTrace]:
    root = root or default_codex_sessions_dir()
    sessions: list[SessionTrace] = []
    for path in iter_session_files(root):
        sessions.append(parse_session_file(path))
        if limit and len(sessions) >= limit:
            break
    return sessions


def _events_from_record(
    record_type: str | None,
    payload: dict[str, Any],
    timestamp: datetime | None,
    calls_by_id: dict[str, tuple[str | None, str | None]],
) -> list[SessionEvent]:
    events: list[SessionEvent] = []

    if record_type == "response_item":
        item_type = payload.get("type")
        role = payload.get("role")
        if item_type == "message":
            text = _extract_text(payload)
            kind, phase = classify_text(role, text)
            events.append(
                SessionEvent(
                    timestamp=timestamp,
                    kind=kind,
                    phase=phase,
                    source_type=record_type,
                    label=f"{role or 'message'} message",
                    text=_compact(text),
                )
            )
        elif item_type in {"function_call", "tool_call"}:
            call_id = payload.get("call_id") or payload.get("id")
            tool_name = payload.get("name") or payload.get("recipient_name") or payload.get("tool_name")
            command = _extract_command(payload)
            if isinstance(call_id, str):
                calls_by_id[call_id] = (tool_name, command)

            nested_calls = _extract_nested_tool_uses(payload)
            if nested_calls:
                for nested_tool, nested_command in nested_calls:
                    kind, phase = classify_tool(nested_tool, nested_command or "")
                    events.append(
                        SessionEvent(
                            timestamp=timestamp,
                            kind=kind,
                            phase=phase,
                            source_type=record_type,
                            label=nested_tool or "tool call",
                            text=_compact(nested_command or ""),
                            tool_name=nested_tool,
                            command=nested_command,
                        )
                    )
                return events

            kind, phase = classify_tool(tool_name, command or json.dumps(payload, ensure_ascii=False))
            events.append(
                SessionEvent(
                    timestamp=timestamp,
                    kind=kind,
                    phase=phase,
                    source_type=record_type,
                    label=tool_name or "tool call",
                    text=_compact(command or ""),
                    tool_name=tool_name,
                    command=command,
                )
            )
        elif item_type in {"function_call_output", "tool_result"}:
            call_id = payload.get("call_id") or payload.get("id")
            previous_tool, previous_command = calls_by_id.get(str(call_id), (None, None))
            text = _extract_text(payload)
            classification_text = f"{previous_command or ''}\n{text}"
            kind, phase = classify_tool(previous_tool, classification_text)
            if _looks_like_error(text):
                kind = EventKind.ERROR
            elif kind == EventKind.TOOL_CALL:
                kind = EventKind.TOOL_RESULT
            events.append(
                SessionEvent(
                    timestamp=timestamp,
                    kind=kind,
                    phase=phase,
                    source_type=record_type,
                    label=f"{previous_tool or 'tool'} result",
                    text=_compact(text),
                    tool_name=previous_tool,
                    command=previous_command,
                )
            )

    elif record_type == "event_msg":
        message = str(payload.get("message") or "")
        if message:
            kind, phase = classify_text("system", message)
            events.append(
                SessionEvent(
                    timestamp=timestamp,
                    kind=kind,
                    phase=phase,
                    source_type=record_type,
                    label=str(payload.get("type") or "event"),
                    text=_compact(message),
                )
            )

    return events


def _extract_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_extract_text(item) for item in value)
    if isinstance(value, dict):
        if "text" in value and isinstance(value["text"], str):
            return value["text"]
        if "content" in value:
            return _extract_text(value["content"])
        if "output" in value:
            return _extract_text(value["output"])
        if "result" in value:
            return _extract_text(value["result"])
        return "\n".join(_extract_text(v) for v in value.values())
    return str(value)


def _extract_command(payload: dict[str, Any]) -> str | None:
    for key in ("command", "cmd"):
        if isinstance(payload.get(key), str):
            return payload[key]
    arguments = payload.get("arguments")
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return arguments
        return _extract_command(parsed) or json.dumps(parsed, ensure_ascii=False)
    if isinstance(arguments, dict):
        return _extract_command(arguments) or json.dumps(arguments, ensure_ascii=False)
    return None


def _extract_nested_tool_uses(payload: dict[str, Any]) -> list[tuple[str | None, str | None]]:
    arguments = payload.get("arguments")
    parsed: Any = arguments
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
        except json.JSONDecodeError:
            return []
    if not isinstance(parsed, dict):
        return []
    tool_uses = parsed.get("tool_uses")
    if not isinstance(tool_uses, list):
        return []

    calls: list[tuple[str | None, str | None]] = []
    for item in tool_uses:
        if not isinstance(item, dict):
            continue
        recipient = item.get("recipient_name") or item.get("name") or item.get("tool_name")
        parameters = item.get("parameters")
        command = None
        if isinstance(parameters, dict):
            command = _extract_command(parameters) or json.dumps(parameters, ensure_ascii=False)
        elif isinstance(parameters, str):
            command = parameters
        calls.append((str(recipient) if recipient else None, command))
    return calls


def _parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _extract_usage(record: dict[str, Any]) -> tuple[int, int, int] | None:
    candidates: list[Any] = []
    payload = record.get("payload")
    if isinstance(payload, dict):
        candidates.extend([payload.get("usage"), payload.get("token_usage"), payload.get("response")])
    candidates.extend([record.get("usage"), record.get("token_usage")])

    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        usage = candidate.get("usage") if isinstance(candidate.get("usage"), dict) else candidate
        input_tokens = _int_from_keys(usage, ("input_tokens", "prompt_tokens", "inputTokenCount"))
        output_tokens = _int_from_keys(usage, ("output_tokens", "completion_tokens", "outputTokenCount"))
        cached_tokens = _int_from_keys(usage, ("cached_tokens", "cached_input_tokens", "cache_read_input_tokens"))
        if input_tokens or output_tokens or cached_tokens:
            return input_tokens, output_tokens, cached_tokens
    return None


def _int_from_keys(mapping: dict[str, Any], keys: tuple[str, ...]) -> int:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
    return 0


def _looks_like_error(text: str) -> bool:
    lower = text.lower()
    return any(token in lower for token in ("exit code: 1", "traceback", "failed", "error", "exception"))


def _compact(text: str, limit: int = 240) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."
