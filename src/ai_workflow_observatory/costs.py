from __future__ import annotations

from .models import CostBreakdown, SessionTrace


# NBP table A average exchange rates from 2026-04-28:
# USD/PLN = 3.6293, EUR/PLN = 4.2470, so USD/EUR = 3.6293 / 4.2470.
USD_TO_EUR = 0.854556
USD_TO_PLN = 3.6293

# Conservative default rates used when exact model pricing is unknown.
# Values are USD per 1M tokens.
MODEL_PRICES = {
    "gpt-5.5": {"input": 1.25, "output": 10.0, "cached": 0.125},
    "gpt-5.4": {"input": 1.25, "output": 10.0, "cached": 0.125},
    "gpt-5.4-mini": {"input": 0.25, "output": 2.0, "cached": 0.025},
    "default": {"input": 1.25, "output": 10.0, "cached": 0.125},
}


def estimate_cost(trace: SessionTrace) -> CostBreakdown:
    input_tokens = trace.input_tokens
    output_tokens = trace.output_tokens
    cached_tokens = trace.cached_tokens
    token_estimate = trace.token_estimate

    if input_tokens == 0 and output_tokens == 0:
        input_chars = 0
        output_chars = 0
        for event in trace.events:
            text_len = len(event.text or "")
            if event.kind.value in {"assistant_message", "final"}:
                output_chars += text_len
            else:
                input_chars += text_len
        input_tokens = max(0, round(input_chars / 4))
        output_tokens = max(0, round(output_chars / 4))
        token_estimate = True

    model = normalize_model(trace.model)
    prices = MODEL_PRICES.get(model, MODEL_PRICES["default"])
    usd = (
        (input_tokens / 1_000_000) * prices["input"]
        + (output_tokens / 1_000_000) * prices["output"]
        + (cached_tokens / 1_000_000) * prices["cached"]
    )

    return CostBreakdown(
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        total_tokens=input_tokens + output_tokens + cached_tokens,
        usd=round(usd, 4),
        eur=round(usd * USD_TO_EUR, 4),
        pln=round(usd * USD_TO_PLN, 4),
        token_estimate=token_estimate,
        pricing_note="exact usage tokens" if not token_estimate else "estimated from session text volume",
    )


def normalize_model(model: str | None) -> str:
    if not model:
        return "default"
    lower = model.lower()
    for key in MODEL_PRICES:
        if key != "default" and key in lower:
            return key
    return lower
