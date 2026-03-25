"""Self-contained AI decision runtime for Phase 3.

This module intentionally lives under `app.engine` so the trading loop can use
it without depending on the placeholder `app.ai` package.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from app.config import (
    AI_PROVIDER_ANTHROPIC,
    AI_PROVIDER_OPENAI,
    ai_api_key_for_provider,
    ai_base_url_for_provider,
    default_ai_model_for_provider,
    get_settings,
    normalize_ai_provider,
)
from app.engine.executor import TradeSignal
from app.models.enums import TradeSide

logger = logging.getLogger(__name__)

# ANSI color codes for terminal log formatting
_CYAN = "\033[96m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_MAGENTA = "\033[95m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"


def _log_ai_prompt(provider: str, model: str, system_prompt: str, symbol: str) -> None:
    print(
        f"\n{_BOLD}{_CYAN}══════════ AI CALL [{provider.upper()}] {model} @ {symbol} ══════════{_RESET}\n"
        f"{_BOLD}{_YELLOW}📋 SYSTEM PROMPT:{_RESET}\n"
        f"{_DIM}{system_prompt}{_RESET}\n",
        flush=True,
    )


def _log_ai_response(provider: str, raw_text: str, symbol: str) -> None:
    print(
        f"\n{_BOLD}{_GREEN}── AI RESPONSE [{provider.upper()}] {symbol} ──{_RESET}\n"
        f"{_BOLD}{_MAGENTA}💬 OUTPUT:{_RESET}\n"
        f"{_DIM}{raw_text}{_RESET}\n"
        f"{_BOLD}{_CYAN}══════════════════════════════════════════{_RESET}\n",
        flush=True,
    )

SETTINGS = get_settings()
AI_CALL_SEMAPHORE = asyncio.Semaphore(max(1, SETTINGS.ai_concurrent_calls))

AI_STRATEGY_ALIASES = {
    "a": "rsi_ma",
    "rsi+ma": "rsi_ma",
    "rsi_ma": "rsi_ma",
    "rsi-ma": "rsi_ma",
    "b": "price_action",
    "price_action": "price_action",
    "price-action": "price_action",
    "c": "volume_macd",
    "volume_macd": "volume_macd",
    "volume-macd": "volume_macd",
    "d": "chart_patterns",
    "chart_patterns": "chart_patterns",
    "chart-patterns": "chart_patterns",
    "hybrid": "hybrid_composite",
    "hybrid_composite": "hybrid_composite",
    "hybrid-composite": "hybrid_composite",
}


@dataclass
class AIUsage:
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost_usdt: Decimal


@dataclass
class AIDecisionResult:
    status: str
    signal: TradeSignal | None = None
    action: str | None = None
    confidence: float | None = None
    reason: str | None = None
    usage: AIUsage | None = None
    raw_response: str | None = None
    error: str | None = None
    skip_reason: str | None = None


@dataclass
class AIValidationResult:
    status: str
    approved: bool | None = None
    confidence_adjustment: float | None = None
    reason: str | None = None
    usage: AIUsage | None = None
    raw_response: str | None = None
    error: str | None = None
    skip_reason: str | None = None


PROMPT_TEMPLATES: dict[str, str] = {
    "rsi_ma": (
        "You are a crypto trading assistant using RSI and moving averages.\n"
        "Prioritize trend continuation, RSI extremes, and crossover confirmation.\n"
        "Return only valid JSON."
    ),
    "price_action": (
        "You are a crypto trading assistant focused on price action.\n"
        "Prioritize support/resistance, momentum, candle structure, and breakouts.\n"
        "Return only valid JSON."
    ),
    "volume_macd": (
        "You are a crypto trading assistant focused on volume and MACD.\n"
        "Prioritize volume confirmation, MACD crossovers, histogram direction, and trend strength.\n"
        "Return only valid JSON."
    ),
    "chart_patterns": (
        "You are a crypto trading assistant focused on chart patterns.\n"
        "Prioritize triangles, flags, double tops/bottoms, channels, and breakout confirmation.\n"
        "Return only valid JSON."
    ),
    "hybrid_composite": (
        "You are a crypto trading assistant for a hybrid composite strategy.\n"
        "Use the provided algorithmic composite score, confidence, and indicator votes as the primary signal.\n"
        "Confirm or challenge that signal using RSI, MACD, SMA, EMA, volume ratio, and flat-market context.\n"
        "Favor HOLD when the composite confidence is weak, volume is dry, or signals conflict.\n"
        "Return only valid JSON."
    ),
}


def normalize_ai_strategy_key(value: str | None, fallback: str = "rsi_ma") -> str:
    key = (value or fallback or "rsi_ma").strip().lower().replace(" ", "_")
    return AI_STRATEGY_ALIASES.get(key, key if key in PROMPT_TEMPLATES else fallback)


def resolve_runtime_provider_and_model(
    context: dict[str, Any],
) -> tuple[str, str]:
    strategy_context = context.get("strategy", {}) if isinstance(context, dict) else {}
    configured_provider = strategy_context.get("ai_provider")
    provider = normalize_ai_provider(str(configured_provider) if configured_provider else SETTINGS.ai_provider)

    configured_model = strategy_context.get("ai_model")
    if configured_model:
        return provider, str(configured_model)

    return provider, str(default_ai_model_for_provider(provider, SETTINGS))


def _system_prompt(strategy_key: str) -> str:
    return (
        f"{PROMPT_TEMPLATES.get(strategy_key, PROMPT_TEMPLATES['rsi_ma'])}\n"
        "You must answer with a single JSON object with these fields:\n"
        '{ "action": "BUY|SELL|HOLD", "quantity_pct": 0.0, "reason": "short rationale", "confidence": 0.0 }\n'
        "Rules:\n"
        "- Make your decision independently based on the market data provided.\n"
        "- Base your analysis ONLY on the actual numeric values in the data. Do not infer or assume trends not visible in the numbers.\n"
        "- RSI reference: < 30 is oversold, 30-40 is approaching oversold, 40-60 is NEUTRAL, 60-70 is approaching overbought, > 70 is overbought.\n"
        "- For moving average crossovers, compare the LAST values: if short MA > long MA the trend is bullish, if short MA < long MA the trend is bearish.\n"
        "- Volume ratio < 0.5 means extremely low volume — low conviction environment.\n"
        "- Use BUY only when you see a clear edge with supporting evidence from multiple data points.\n"
        "- Use SELL only when there is an open position and the setup is bearish.\n"
        "- Use HOLD when signals are mixed, unclear, or volume is too low to trust.\n"
        "- quantity_pct must be between 0 and 1.\n"
        "- confidence must honestly reflect the strength of evidence (mixed signals = low confidence).\n"
        "- Do not wrap the JSON in markdown or add extra commentary."
    )


def _validation_system_prompt(proposed_action: str) -> str:
    return (
        "You are a crypto trade validator.\n"
        f"The algorithm already proposed a {proposed_action} trade.\n"
        "You cannot create a new trade direction and you cannot reverse the action.\n"
        "Return exactly one JSON object with these fields:\n"
        '{ "approve": true, "confidence_adjustment": -0.10, "reason": "short rationale" }\n'
        "Rules:\n"
        "- approve must be true or false.\n"
        "- confidence_adjustment must be between -0.30 and 0.00.\n"
        "- Use false only when the setup quality is poor or the risk is unacceptable.\n"
        "- Never return a positive confidence adjustment.\n"
        "- Base your answer only on the supplied numeric context.\n"
        "- Do not add markdown or commentary outside the JSON object."
    )


def _extract_anthropic_text(response_json: dict[str, Any]) -> str:
    content = response_json.get("content", [])
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        if parts:
            return "\n".join(parts).strip()
    text = response_json.get("text")
    return str(text).strip() if text is not None else ""


def _extract_openai_text(response_json: dict[str, Any]) -> str:
    choices = response_json.get("choices", [])
    if not isinstance(choices, list) or not choices:
        return ""

    message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
    content = message.get("content", "")
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
                parts.append(str(item.get("text", "")))
        return "\n".join(part for part in parts if part).strip()
    return str(content).strip()


def _extract_json_payload(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        payload = json.loads(cleaned)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        payload = json.loads(match.group(0))
        if isinstance(payload, dict):
            return payload

    raise ValueError("AI response did not contain valid JSON")


def _quantize_cost(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.00000001"))


# Per-model pricing: (input_cost_per_1m, output_cost_per_1m)
# These are used when the model name from the API response matches a key.
MODEL_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI GPT-5.4 family
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4-pro": (30.00, 180.00),
    # OpenAI GPT-4o family
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    # Anthropic Claude family
    "claude-opus-4-6": (15.00, 75.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-3-5-sonnet-20240620": (3.00, 15.00),
    "claude-3-5-sonnet-latest": (3.00, 15.00),
    "claude-3-haiku-20240307": (0.25, 1.25),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
}


def _get_model_pricing(model: str, provider: str) -> tuple[float, float]:
    """Look up per-model pricing. Falls back to provider-level config rates."""
    if model in MODEL_PRICING:
        return MODEL_PRICING[model]
    # Try prefix matching (e.g. "gpt-5.4-mini-2026-03-01" -> "gpt-5.4-mini")
    for key in sorted(MODEL_PRICING, key=len, reverse=True):
        if model.startswith(key):
            return MODEL_PRICING[key]
    # Fallback to config-level rates
    normalized = normalize_ai_provider(provider)
    if normalized == AI_PROVIDER_OPENAI:
        return (SETTINGS.openai_input_cost_per_1m_tokens_usd, SETTINGS.openai_output_cost_per_1m_tokens_usd)
    return (SETTINGS.ai_input_cost_per_1m_tokens_usd, SETTINGS.ai_output_cost_per_1m_tokens_usd)


def _estimate_cost(provider: str, prompt_tokens: int, completion_tokens: int, model: str = "") -> Decimal:
    input_rate, output_rate = _get_model_pricing(model, provider)
    prompt_cost = Decimal(prompt_tokens) * Decimal(str(input_rate)) / Decimal("1000000")
    completion_cost = Decimal(completion_tokens) * Decimal(str(output_rate)) / Decimal("1000000")
    return _quantize_cost(prompt_cost + completion_cost)


def _usage_from_response(response_json: dict[str, Any], provider: str) -> AIUsage:
    usage = response_json.get("usage") or {}
    normalized_provider = normalize_ai_provider(provider)
    if normalized_provider == AI_PROVIDER_OPENAI:
        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        default_model = SETTINGS.openai_model
    else:
        prompt_tokens = int(usage.get("input_tokens", 0) or 0)
        completion_tokens = int(usage.get("output_tokens", 0) or 0)
        default_model = SETTINGS.anthropic_model
    total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens) or (prompt_tokens + completion_tokens))
    model = str(response_json.get("model") or default_model)
    return AIUsage(
        provider=normalized_provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated_cost_usdt=_estimate_cost(normalized_provider, prompt_tokens, completion_tokens, model),
    )


def _coerce_signal(payload: dict[str, Any], *, symbol: str, has_position: bool) -> TradeSignal | None:
    action = str(payload.get("action", "HOLD")).strip().upper()
    if action not in {"BUY", "SELL", "HOLD"}:
        raise ValueError(f"Unsupported action: {action}")

    if action == "HOLD":
        return None

    if action == "SELL" and not has_position:
        return None

    quantity_raw = payload.get("quantity_pct", payload.get("quantity", 1.0 if action == "SELL" else 0.5))
    quantity_pct = Decimal(str(quantity_raw))
    if quantity_pct < 0:
        quantity_pct = Decimal("0")
    if quantity_pct > 1:
        quantity_pct = Decimal("1")

    reason = str(payload.get("reason", "")).strip()
    return TradeSignal(
        action=TradeSide[action],
        symbol=symbol,
        quantity_pct=quantity_pct,
        reason=reason,
    )


def _coerce_confidence(payload: dict[str, Any]) -> float | None:
    raw_confidence = payload.get("confidence")
    if raw_confidence is None:
        return None

    confidence = float(raw_confidence)
    if confidence < 0:
        return 0.0
    if confidence > 1:
        return 1.0
    return confidence


def _coerce_validation_payload(payload: dict[str, Any]) -> tuple[bool, float, str]:
    approved = bool(payload.get("approve", True))
    raw_adjustment = float(payload.get("confidence_adjustment", 0.0) or 0.0)
    adjustment = max(-0.30, min(0.0, raw_adjustment))
    reason = str(payload.get("reason", "")).strip() or "AI validation"
    return approved, adjustment, reason


def _flat_market_metrics(
    closes: list[float],
    threshold_pct: float,
    atr_values: list[float] | None = None,
) -> tuple[bool, dict[str, float]]:
    if len(closes) < 10:
        return False, {}

    sample = closes[-20:]
    first = sample[0]
    last = sample[-1]
    high = max(sample)
    low = min(sample)
    if first <= 0 or high <= 0 or low <= 0:
        return False, {}

    drift_pct = abs(last - first) / first * 100
    midpoint = (high + low) / 2
    range_pct = ((high - low) / midpoint * 100) if midpoint > 0 else 0.0
    metrics: dict[str, float] = {
        "drift_pct": drift_pct,
        "range_pct": range_pct,
        "threshold_pct": threshold_pct,
    }

    # ATR-based flat detection: if latest ATR / price < 0.5%, market is quiet
    if atr_values and last > 0:
        atr_pct = atr_values[-1] / last * 100
        metrics["atr_pct"] = atr_pct
        if atr_pct < 0.5:
            return True, metrics

    return max(drift_pct, range_pct) < threshold_pct, metrics


def analyze_flat_market(
    closes: list[float],
    threshold_pct: float | None = None,
    atr_values: list[float] | None = None,
) -> tuple[bool, dict[str, float]]:
    """Public wrapper for flat-market gating and prompt context."""
    return _flat_market_metrics(
        closes,
        threshold_pct or SETTINGS.ai_flat_market_threshold_pct,
        atr_values=atr_values,
    )


def build_ai_context(
    *,
    strategy_id: str,
    strategy_name: str,
    symbol: str,
    interval: str,
    closes: list[float],
    indicators: dict[str, Any],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[float] | None = None,
    wallet_available_usdt: Decimal,
    has_position: bool,
    position_quantity: Decimal | None,
    position_entry_price: Decimal | None,
    current_price: Decimal,
    ai_strategy_key: str,
    ai_provider: str,
    ai_model: str,
    ai_cooldown_seconds: int,
    ai_max_tokens: int,
    ai_temperature: Decimal,
    flat_market_metrics: dict[str, float],
    algorithmic_signal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    indicator_snapshot: dict[str, Any] = {}
    for key, value in indicators.items():
        if isinstance(value, tuple):
            indicator_snapshot[key] = [list(part[-30:]) if isinstance(part, list) else part for part in value]
        elif isinstance(value, list):
            indicator_snapshot[key] = value[-30:]
        else:
            indicator_snapshot[key] = value

    recent_closes = closes[-100:]

    # Unrealized P&L for open positions
    unrealized_pnl = 0.0
    unrealized_pnl_pct = 0.0
    if has_position and position_entry_price is not None and position_quantity is not None:
        unrealized_pnl = float((current_price - position_entry_price) * position_quantity)
        if position_entry_price > 0:
            unrealized_pnl_pct = float((current_price / position_entry_price - 1) * 100)

    return {
        "strategy": {
            "id": strategy_id,
            "name": strategy_name,
            "ai_strategy_key": ai_strategy_key,
            "ai_provider": normalize_ai_provider(ai_provider),
            "ai_model": ai_model,
            "ai_cooldown_seconds": ai_cooldown_seconds,
            "ai_max_tokens": ai_max_tokens,
            "ai_temperature": float(ai_temperature),
        },
        "market": {
            "symbol": symbol,
            "interval": interval,
            "current_price": float(current_price),
            "recent_closes": recent_closes,
            "recent_highs": list((highs or [])[-100:]),
            "recent_lows": list((lows or [])[-100:]),
            "recent_volumes": list((volumes or [])[-100:]),
            "flat_market_metrics": flat_market_metrics,
        },
        "indicators": indicator_snapshot,
        **({"algorithmic_signal": algorithmic_signal} if algorithmic_signal else {}),
        "portfolio": {
            "available_usdt": float(wallet_available_usdt),
            "has_position": has_position,
            "position_quantity": float(position_quantity) if position_quantity is not None else 0.0,
            "position_entry_price": float(position_entry_price) if position_entry_price is not None else None,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": unrealized_pnl_pct,
        },
    }


async def _call_anthropic(
    *,
    client: httpx.AsyncClient,
    model: str,
    max_tokens: int,
    temperature: Decimal,
    system_prompt: str,
    user_message: str,
) -> dict[str, Any]:
    response = await client.post(
        "/v1/messages",
        headers={
            "x-api-key": SETTINGS.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": max_tokens,
            "temperature": float(temperature),
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": user_message,
                }
            ],
        },
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("Anthropic response was not a JSON object")
    return payload


async def _call_openai(
    *,
    client: httpx.AsyncClient,
    model: str,
    max_tokens: int,
    temperature: Decimal,
    system_prompt: str,
    user_message: str,
) -> dict[str, Any]:
    # Newer OpenAI models (gpt-4o, gpt-5, o-series) require
    # "max_completion_tokens" instead of the legacy "max_tokens".
    _new_api_models = ("gpt-4o", "gpt-5", "o1", "o3", "o4")
    use_new_param = any(model.startswith(prefix) for prefix in _new_api_models)
    uses_fixed_temperature = model.startswith("gpt-5")
    token_key = "max_completion_tokens" if use_new_param else "max_tokens"
    request_body = {
        "model": model,
        token_key: max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    }
    if not uses_fixed_temperature:
        request_body["temperature"] = float(temperature)
    logger.info("openai request model=%s max_tokens=%d msg_len=%d", model, max_tokens, len(user_message))
    response = await client.post(
        "/chat/completions",
        headers={
            "authorization": f"Bearer {SETTINGS.openai_api_key}",
            "content-type": "application/json",
        },
        json=request_body,
    )
    if response.status_code != 200:
        logger.error("openai error status=%d body=%s", response.status_code, response.text[:500])
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("OpenAI response was not a JSON object")
    return payload


async def evaluate_ai_decision(
    *,
    strategy_key: str,
    context: dict[str, Any],
    force: bool = False,
) -> AIDecisionResult:
    closes = list(context.get("market", {}).get("recent_closes") or [])
    market_context = context.get("market", {})
    flat_threshold = (
        market_context.get("flat_market_metrics", {}).get("threshold_pct")
        if isinstance(market_context.get("flat_market_metrics"), dict)
        else None
    )
    is_flat, metrics = _flat_market_metrics(
        closes,
        float(flat_threshold or SETTINGS.ai_flat_market_threshold_pct),
    )
    if is_flat and not force:
        return AIDecisionResult(
            status="skipped",
            reason="Flat market detected; AI call skipped",
            skip_reason="flat_market",
        )

    provider, model = resolve_runtime_provider_and_model(context)
    if provider == AI_PROVIDER_OPENAI:
        api_key = ai_api_key_for_provider(provider, SETTINGS)
        base_url = ai_base_url_for_provider(provider, SETTINGS)
        provider_label = "OpenAI"
    else:
        api_key = ai_api_key_for_provider(provider, SETTINGS)
        base_url = ai_base_url_for_provider(provider, SETTINGS)
        provider_label = "Anthropic"

    if not api_key:
        return AIDecisionResult(
            status="skipped",
            reason=f"{provider_label} API key is not configured",
            skip_reason="missing_api_key",
        )

    max_tokens = int(context.get("strategy", {}).get("ai_max_tokens") or SETTINGS.ai_max_tokens)
    temperature = Decimal(str(context.get("strategy", {}).get("ai_temperature") or SETTINGS.ai_temperature))
    normalized_key = normalize_ai_strategy_key(strategy_key)
    payload_context = dict(context)
    market_context = payload_context.setdefault("market", {})
    existing_metrics = market_context.get("flat_market_metrics")
    if isinstance(existing_metrics, dict):
        merged_metrics = {**metrics, **existing_metrics}
    else:
        merged_metrics = metrics
    market_context["flat_market_metrics"] = merged_metrics
    user_message = json.dumps(payload_context, separators=(",", ":"), default=str)

    last_error: str | None = None
    last_usage: AIUsage | None = None
    system_prompt = _system_prompt(normalized_key)

    async with AI_CALL_SEMAPHORE:
        async with httpx.AsyncClient(base_url=base_url, timeout=SETTINGS.ai_timeout_seconds) as client:
            for attempt in range(2):
                try:
                    prompt = system_prompt if attempt == 0 else f"{system_prompt}\nPrevious response was invalid. Return only strict JSON."
                    _symbol = str(context.get("market", {}).get("symbol") or "BTCUSDT")
                    _log_ai_prompt(provider, model, prompt, _symbol)
                    print(f"{_BOLD}{_YELLOW}⏳ Waiting for {provider.upper()} response...{_RESET}", flush=True)
                    t0 = time.monotonic()
                    if provider == AI_PROVIDER_OPENAI:
                        response_json = await _call_openai(
                            client=client,
                            model=model,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            system_prompt=prompt,
                            user_message=user_message,
                        )
                        raw_text = _extract_openai_text(response_json)
                    else:
                        response_json = await _call_anthropic(
                            client=client,
                            model=model,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            system_prompt=prompt,
                            user_message=user_message,
                        )
                        raw_text = _extract_anthropic_text(response_json)
                    elapsed = time.monotonic() - t0
                    print(f"{_BOLD}{_GREEN}✅ Response received in {elapsed:.2f}s{_RESET}", flush=True)
                    _log_ai_response(provider, raw_text or "(empty)", _symbol)
                    if not raw_text:
                        raise ValueError(f"{provider_label} response did not contain text content")
                    last_usage = _usage_from_response(response_json, provider)
                    payload = _extract_json_payload(raw_text)
                    confidence = _coerce_confidence(payload)
                    action = str(payload.get("action", "HOLD")).strip().upper()
                    signal = _coerce_signal(
                        payload,
                        symbol=str(context.get("market", {}).get("symbol") or "BTCUSDT"),
                        has_position=bool(context.get("portfolio", {}).get("has_position")),
                    )
                    if signal is None:
                        return AIDecisionResult(
                            status="hold",
                            action=action,
                            confidence=confidence,
                            reason=str(payload.get("reason", "")).strip() or "AI returned HOLD",
                            usage=last_usage,
                            raw_response=raw_text,
                        )

                    return AIDecisionResult(
                        status="signal",
                        signal=signal,
                        action=signal.action.value,
                        confidence=confidence,
                        reason=signal.reason or "AI returned a tradable signal",
                        usage=last_usage,
                        raw_response=raw_text,
                    )
                except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
                    last_error = str(exc)
                    logger.warning(
                        "ai decision retry provider=%s attempt=%d error=%s",
                        provider,
                        attempt + 1,
                        exc,
                    )
                    if attempt == 0:
                        continue

    return AIDecisionResult(
        status="error",
        reason="AI decision failed; defaulted to HOLD",
        error=last_error,
        usage=last_usage,
    )


async def evaluate_ai_validation(
    *,
    context: dict[str, Any],
    proposed_action: str,
) -> AIValidationResult:
    provider, model = resolve_runtime_provider_and_model(context)
    api_key = ai_api_key_for_provider(provider, SETTINGS)
    base_url = ai_base_url_for_provider(provider, SETTINGS)
    provider_label = "OpenAI" if provider == AI_PROVIDER_OPENAI else "Anthropic"

    if not api_key:
        return AIValidationResult(
            status="skipped",
            reason=f"{provider_label} API key is not configured",
            skip_reason="missing_api_key",
        )

    max_tokens = int(context.get("strategy", {}).get("ai_max_tokens") or SETTINGS.ai_max_tokens)
    temperature = Decimal(str(context.get("strategy", {}).get("ai_temperature") or SETTINGS.ai_temperature))
    user_message = json.dumps(context, separators=(",", ":"), default=str)
    system_prompt = _validation_system_prompt(proposed_action)
    last_error: str | None = None
    last_usage: AIUsage | None = None

    async with AI_CALL_SEMAPHORE:
        async with httpx.AsyncClient(base_url=base_url, timeout=SETTINGS.ai_timeout_seconds) as client:
            for attempt in range(2):
                try:
                    prompt = system_prompt if attempt == 0 else f"{system_prompt}\nPrevious response was invalid. Return only strict JSON."
                    symbol = str(context.get("market", {}).get("symbol") or "BTCUSDT")
                    _log_ai_prompt(provider, model, prompt, symbol)
                    print(f"{_BOLD}{_YELLOW}⏳ Waiting for {provider.upper()} validation...{_RESET}", flush=True)
                    t0 = time.monotonic()
                    if provider == AI_PROVIDER_OPENAI:
                        response_json = await _call_openai(
                            client=client,
                            model=model,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            system_prompt=prompt,
                            user_message=user_message,
                        )
                        raw_text = _extract_openai_text(response_json)
                    else:
                        response_json = await _call_anthropic(
                            client=client,
                            model=model,
                            max_tokens=max_tokens,
                            temperature=temperature,
                            system_prompt=prompt,
                            user_message=user_message,
                        )
                        raw_text = _extract_anthropic_text(response_json)
                    elapsed = time.monotonic() - t0
                    print(f"{_BOLD}{_GREEN}✅ Validation received in {elapsed:.2f}s{_RESET}", flush=True)
                    _log_ai_response(provider, raw_text or "(empty)", symbol)
                    if not raw_text:
                        raise ValueError(f"{provider_label} validation response did not contain text content")
                    last_usage = _usage_from_response(response_json, provider)
                    payload = _extract_json_payload(raw_text)
                    approved, confidence_adjustment, reason = _coerce_validation_payload(payload)
                    return AIValidationResult(
                        status="validated" if approved else "rejected",
                        approved=approved,
                        confidence_adjustment=confidence_adjustment,
                        reason=reason,
                        usage=last_usage,
                        raw_response=raw_text,
                    )
                except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
                    last_error = str(exc)
                    logger.warning(
                        "ai validation retry provider=%s attempt=%d error=%s",
                        provider,
                        attempt + 1,
                        exc,
                    )
                    if attempt == 0:
                        continue

    return AIValidationResult(
        status="error",
        reason="AI validation failed; continuing without validator",
        error=last_error,
        usage=last_usage,
    )
