from __future__ import annotations

import json
from pathlib import Path

from ai_workflow_observatory.models import EventKind
from ai_workflow_observatory.parser import parse_session_file


def test_parse_codex_jsonl_session(tmp_path: Path) -> None:
    session_file = tmp_path / "rollout-test.jsonl"
    records = [
        {
            "timestamp": "2026-04-28T10:00:00.000Z",
            "type": "session_meta",
            "payload": {
                "id": "abc",
                "timestamp": "2026-04-28T10:00:00.000Z",
                "cwd": "C:\\Users\\syfsy\\projekty\\demo",
            },
        },
        {
            "timestamp": "2026-04-28T10:01:00.000Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "shell_command",
                "arguments": json.dumps({"command": "rg service src"}),
            },
        },
        {
            "timestamp": "2026-04-28T10:02:00.000Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "apply_patch",
                "arguments": "*** Begin Patch",
            },
        },
    ]
    session_file.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")

    trace = parse_session_file(session_file)

    assert trace.session_id == "abc"
    assert trace.project == "demo"
    assert [event.kind for event in trace.events] == [EventKind.SEARCH, EventKind.EDIT]
