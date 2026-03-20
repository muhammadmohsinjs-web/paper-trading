from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.engine.ai_runtime import MODEL_PRICING, _get_model_pricing


def estimate_cost(
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    input_cost_per_1m_tokens_usd: float = 3.0,
    output_cost_per_1m_tokens_usd: float = 15.0,
    usage: Any | None = None,
    response: Any | None = None,
    model: str | None = None,
    strategy_id: str | None = None,
) -> Decimal:
    """Estimate token cost in USD/USDT-equivalent using model-based pricing."""
    del strategy_id

    if response is not None:
        usage = getattr(response, "usage", usage)
        input_tokens = int(getattr(response, "input_tokens", input_tokens) or input_tokens)
        output_tokens = int(getattr(response, "output_tokens", output_tokens) or output_tokens)
        if model is None:
            model = getattr(response, "model", None)

    if usage is not None:
        input_tokens = int(getattr(usage, "input_tokens", input_tokens) or input_tokens)
        output_tokens = int(getattr(usage, "output_tokens", output_tokens) or output_tokens)

    # Use model-based pricing if model is known
    if model and model in MODEL_PRICING:
        input_cost_per_1m_tokens_usd, output_cost_per_1m_tokens_usd = MODEL_PRICING[model]

    input_cost = (
        Decimal(input_tokens) * Decimal(str(input_cost_per_1m_tokens_usd)) / Decimal("1000000")
    )
    output_cost = (
        Decimal(output_tokens) * Decimal(str(output_cost_per_1m_tokens_usd)) / Decimal("1000000")
    )
    return (input_cost + output_cost).quantize(Decimal("0.00000001"))
