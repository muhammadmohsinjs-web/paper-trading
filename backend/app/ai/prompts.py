from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

from app.ai.types import AIStrategyProfile, MarketSnapshot


@dataclass
class PromptBundle:
    system: str
    user: str


class StrategyPromptBuilder:
    """Builds strategy-specific prompts for AI trading decisions."""

    def build(self, profile: AIStrategyProfile | str, snapshot: MarketSnapshot) -> PromptBundle:
        strategy = self._coerce_profile(profile)
        system = self._build_system_prompt(strategy)
        user = self._build_user_prompt(strategy, snapshot)
        return PromptBundle(system=system, user=user)

    def resolve_profile(self, profile: AIStrategyProfile | str) -> AIStrategyProfile:
        return self._coerce_profile(profile)

    def _coerce_profile(self, profile: AIStrategyProfile | str) -> AIStrategyProfile:
        if isinstance(profile, AIStrategyProfile):
            return profile
        return AIStrategyProfile.from_value(profile)

    def _build_system_prompt(self, profile: AIStrategyProfile) -> str:
        strategy_guidance = {
            AIStrategyProfile.RSI_MA: (
                "Use RSI, moving averages, and trend strength to decide whether momentum is "
                "supportive of a buy, sell, or hold."
            ),
            AIStrategyProfile.PRICE_ACTION: (
                "Use candle structure, support/resistance, breakouts, rejections, and recent "
                "price behavior."
            ),
            AIStrategyProfile.VOLUME_MACD: (
                "Use volume expansion/contraction, MACD direction, and histogram momentum to "
                "judge whether a move has confirmation."
            ),
            AIStrategyProfile.CHART_PATTERNS: (
                "Use chart patterns, neckline/breakout logic, and pattern failure signals."
            ),
        }[profile]

        return (
            "You are an execution-focused trading analyst. "
            "Return exactly one JSON object and nothing else. "
            "The object must contain: action, quantity_pct, reason, confidence, symbol. "
            "action must be one of BUY, SELL, HOLD. "
            "quantity_pct must be a number between 0 and 1. "
            "If the market is flat, noisy, or inconclusive, return HOLD with quantity_pct 0. "
            f"Strategy guidance: {strategy_guidance}"
        )

    def _build_user_prompt(self, profile: AIStrategyProfile, snapshot: MarketSnapshot) -> str:
        sections = [
            f"Strategy profile: {profile.value}",
            f"Symbol: {snapshot.symbol}",
            f"Interval: {snapshot.interval}",
            f"Current price: {snapshot.current_price}",
            f"Has position: {snapshot.has_position}",
            f"Position quantity: {snapshot.position_quantity if snapshot.position_quantity is not None else 'none'}",
            f"Entry price: {snapshot.entry_price if snapshot.entry_price is not None else 'none'}",
            f"Available USDT: {snapshot.available_usdt if snapshot.available_usdt is not None else 'none'}",
            f"Initial balance USDT: {snapshot.initial_balance_usdt if snapshot.initial_balance_usdt is not None else 'none'}",
            "",
            "Recent closes: " + self._format_series(snapshot.closes, max_items=24),
            "Recent highs: " + self._format_series(snapshot.highs, max_items=24),
            "Recent lows: " + self._format_series(snapshot.lows, max_items=24),
            "Recent volumes: " + self._format_series(snapshot.volumes, max_items=24),
            "",
            "Indicators:",
            self._format_indicators(snapshot.indicators),
        ]
        if snapshot.notes:
            sections.extend(["", "Notes:", *[f"- {note}" for note in snapshot.notes]])
        sections.extend(
            [
                "",
                "Return JSON in this schema:",
                '{'
                '"action":"BUY|SELL|HOLD",'
                '"quantity_pct":0.0,'
                '"reason":"brief explanation",'
                '"confidence":0.0,'
                f'"symbol":"{snapshot.symbol}"'
                "}",
            ]
        )
        return "\n".join(sections)

    def _format_series(self, values: Iterable[Decimal], max_items: int = 24) -> str:
        series = list(values)[-max_items:]
        if not series:
            return "[]"
        return "[" + ", ".join(str(value) for value in series) + "]"

    def _format_indicators(self, indicators: dict[str, object]) -> str:
        if not indicators:
            return "- none"
        lines = []
        for key, value in indicators.items():
            lines.append(f"- {key}: {value}")
        return "\n".join(lines)
