from __future__ import annotations

from pathlib import Path

from ai_workflow_observatory.costs import estimate_cost
from ai_workflow_observatory.models import SessionTrace


def test_estimate_cost_from_real_usage_tokens() -> None:
    trace = SessionTrace(
        session_id="s1",
        path=Path("s1.jsonl"),
        model="gpt-5.5",
        input_tokens=1_000_000,
        output_tokens=100_000,
        token_estimate=False,
    )

    cost = estimate_cost(trace)

    assert cost.usd == 2.25
    assert cost.eur > 0
    assert cost.pln > 0
    assert cost.token_estimate is False


def test_estimate_cost_from_session_text_when_usage_missing() -> None:
    trace = SessionTrace(session_id="s2", path=Path("s2.jsonl"), model="unknown")

    cost = estimate_cost(trace)

    assert cost.usd == 0
    assert cost.token_estimate is True
