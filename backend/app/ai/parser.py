from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Awaitable, Callable

from app.ai.types import AITradeAction, TradeDecision


@dataclass
class DecisionParseResult:
    decision: TradeDecision
    valid: bool
    error: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class DecisionParser:
    """Parse model JSON into trade decisions with one repair retry."""

    def parse(self, text: str, default_symbol: str) -> DecisionParseResult:
        try:
            payload = self._extract_payload(text)
            decision = self._payload_to_decision(payload, default_symbol)
            return DecisionParseResult(decision=decision, valid=True, payload=payload)
        except Exception as exc:
            return DecisionParseResult(
                decision=self._fallback_hold(default_symbol, str(exc)),
                valid=False,
                error=str(exc),
            )

    async def parse_with_retry(
        self,
        text: str,
        default_symbol: str,
        repair_call: Callable[[str], Awaitable[str]] | None = None,
    ) -> DecisionParseResult:
        first = self.parse(text, default_symbol)
        if first.valid or repair_call is None:
            return first

        repair_prompt = self._build_repair_prompt(text, first.error or "invalid JSON")
        repaired_text = await repair_call(repair_prompt)
        second = self.parse(repaired_text, default_symbol)
        if second.valid:
            second.decision.repaired = True
            return second

        fallback = self._fallback_hold(
            default_symbol,
            second.error or first.error or "invalid model output",
        )
        fallback.repaired = True
        return DecisionParseResult(
            decision=fallback,
            valid=False,
            error=second.error or first.error,
        )

    def _build_repair_prompt(self, raw_text: str, error: str) -> str:
        return (
            "The previous response was invalid JSON and must be repaired. "
            f"Error: {error}. "
            "Return only a single valid JSON object with keys action, quantity_pct, reason, confidence, symbol. "
            f"Previous response: {raw_text}"
        )

    def _extract_payload(self, text: str) -> dict[str, Any]:
        stripped = text.strip()
        stripped = self._strip_code_fences(stripped)

        decoder = json.JSONDecoder()
        for candidate in self._json_candidates(stripped):
            try:
                payload, _ = decoder.raw_decode(candidate)
                if isinstance(payload, dict):
                    return payload
            except json.JSONDecodeError:
                continue

        parsed = json.loads(stripped)
        if not isinstance(parsed, dict):
            raise ValueError("Decision output must be a JSON object")
        return parsed

    def _json_candidates(self, text: str) -> list[str]:
        candidates = [text]
        for marker in ("{", "["):
            idx = text.find(marker)
            if idx >= 0:
                candidates.append(text[idx:].strip())
        return candidates

    def _strip_code_fences(self, text: str) -> str:
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 2:
                return "\n".join(lines[1:-1]).strip()
        return text

    def _payload_to_decision(self, payload: dict[str, Any], default_symbol: str) -> TradeDecision:
        action = self._normalize_action(payload.get("action") or payload.get("side") or payload.get("decision"))
        symbol = str(payload.get("symbol") or default_symbol)
        quantity_pct = self._normalize_quantity(payload.get("quantity_pct"), action)
        confidence = self._normalize_confidence(payload.get("confidence"))
        reason = str(payload.get("reason") or payload.get("rationale") or payload.get("explanation") or "")

        metadata = {
            key: value
            for key, value in payload.items()
            if key not in {"action", "side", "decision", "symbol", "quantity_pct", "confidence", "reason", "rationale", "explanation"}
        }

        return TradeDecision(
            action=action,
            symbol=symbol,
            quantity_pct=quantity_pct,
            reason=reason,
            confidence=confidence,
            metadata=metadata,
            raw_payload=payload,
        )

    def _normalize_action(self, value: Any) -> AITradeAction:
        if value is None:
            return AITradeAction.HOLD
        normalized = str(value).strip().lower()
        aliases = {
            "buy": AITradeAction.BUY,
            "long": AITradeAction.BUY,
            "sell": AITradeAction.SELL,
            "short": AITradeAction.SELL,
            "hold": AITradeAction.HOLD,
            "neutral": AITradeAction.HOLD,
            "wait": AITradeAction.HOLD,
            "none": AITradeAction.HOLD,
        }
        action = aliases.get(normalized)
        if action is None:
            raise ValueError(f"Unknown action: {value}")
        return action

    def _normalize_quantity(self, value: Any, action: AITradeAction) -> Decimal:
        if action == AITradeAction.HOLD:
            return Decimal("0")
        if value is None or value == "":
            return Decimal("1")
        quantity = Decimal(str(value))
        if quantity > 1:
            quantity = quantity / Decimal("100")
        return self._clamp_decimal(quantity, Decimal("0"), Decimal("1"))

    def _normalize_confidence(self, value: Any) -> float | None:
        if value is None or value == "":
            return None
        confidence = float(value)
        if confidence > 1:
            confidence = confidence / 100.0
        confidence = max(0.0, min(confidence, 1.0))
        return confidence

    def _fallback_hold(self, default_symbol: str, error: str) -> TradeDecision:
        return TradeDecision(
            action=AITradeAction.HOLD,
            symbol=default_symbol,
            quantity_pct=Decimal("0"),
            reason=f"Fallback HOLD after invalid AI output: {error}",
            confidence=0.0,
        )

    def _clamp_decimal(self, value: Decimal, minimum: Decimal, maximum: Decimal) -> Decimal:
        if value < minimum:
            return minimum
        if value > maximum:
            return maximum
        return value


def parse_trade_signal(text: str, default_symbol: str = "BTCUSDT") -> TradeDecision:
    """Compatibility helper for direct parser use in tests and callers."""
    return DecisionParser().parse(text, default_symbol).decision
