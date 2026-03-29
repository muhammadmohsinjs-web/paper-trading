from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import re
from typing import Any

from app.config import get_settings

SETTINGS = get_settings()

LIQUIDITY_ARCHETYPE_MAJOR = "major"
LIQUIDITY_ARCHETYPE_MID = "mid"
LIQUIDITY_ARCHETYPE_SMALL = "small"
LIQUIDITY_ARCHETYPE_MEME = "meme"

_MEME_PATTERN = re.compile(
    r"(DOGE|SHIB|PEPE|WIF|BONK|FLOKI|BRETT|MOG|MEME|POPCAT|MEW|NEIRO|CHEEMS|PONKE|TURBO|BOME|1000)",
    re.IGNORECASE,
)

_UNIVERSE_DISCOVERY_RATIO = {
    LIQUIDITY_ARCHETYPE_MAJOR: 0.60,
    LIQUIDITY_ARCHETYPE_MID: 0.60,
    LIQUIDITY_ARCHETYPE_SMALL: 0.75,
    LIQUIDITY_ARCHETYPE_MEME: 0.60,
}
_SCANNER_INTERVAL_SOFT_RATIO = {
    LIQUIDITY_ARCHETYPE_MAJOR: 0.50,
    LIQUIDITY_ARCHETYPE_MID: 0.70,
    LIQUIDITY_ARCHETYPE_SMALL: 0.70,
    LIQUIDITY_ARCHETYPE_MEME: 0.80,
}
_SCANNER_INTERVAL_HARD_RATIO = {
    LIQUIDITY_ARCHETYPE_MAJOR: 0.10,
    LIQUIDITY_ARCHETYPE_MID: 0.20,
    LIQUIDITY_ARCHETYPE_SMALL: 0.25,
    LIQUIDITY_ARCHETYPE_MEME: 0.35,
}


@dataclass(frozen=True)
class LiquidityPolicy:
    archetype: str
    base_daily_floor_usdt: float
    required_24h_volume_usdt: float
    discovery_floor_usdt: float
    interval_expected_volume_usdt: float
    interval_soft_floor_usdt: float
    interval_hard_floor_usdt: float


def _resolve_base_asset(symbol: str, quote_asset: str | None = None) -> str:
    normalized = (symbol or "").upper()
    suffix = (quote_asset or SETTINGS.default_quote_asset).upper()
    if normalized.endswith(suffix):
        return normalized[: -len(suffix)]
    return normalized


def _coerce_base_set(raw: Any, default: list[str]) -> set[str]:
    if isinstance(raw, str):
        items = [item.strip().upper() for item in raw.split(",") if item.strip()]
        return set(items or [item.upper() for item in default])
    if isinstance(raw, list):
        items = [str(item).strip().upper() for item in raw if str(item).strip()]
        return set(items or [item.upper() for item in default])
    return {item.upper() for item in default}


def resolve_interval_hours(interval: str | None) -> float:
    normalized = (interval or "1h").strip().lower()
    if normalized.endswith("m"):
        try:
            return max(float(int(normalized[:-1])) / 60.0, 1.0 / 60.0)
        except ValueError:
            return 1.0
    if normalized.endswith("h"):
        try:
            return max(float(int(normalized[:-1])), 1.0)
        except ValueError:
            return 1.0
    if normalized.endswith("d"):
        try:
            return max(float(int(normalized[:-1])) * 24.0, 24.0)
        except ValueError:
            return 24.0
    return 1.0


def infer_liquidity_archetype(
    symbol: str,
    *,
    observed_volume_24h_usdt: float = 0.0,
    config: dict[str, Any] | None = None,
) -> str:
    source = config or {}
    base_asset = _resolve_base_asset(symbol)
    meme_bases = _coerce_base_set(source.get("liquidity_meme_bases"), SETTINGS.liquidity_meme_bases)
    major_bases = _coerce_base_set(source.get("liquidity_major_bases"), SETTINGS.liquidity_major_bases)

    if base_asset in meme_bases or _MEME_PATTERN.search(base_asset):
        return LIQUIDITY_ARCHETYPE_MEME
    if base_asset in major_bases:
        return LIQUIDITY_ARCHETYPE_MAJOR
    if observed_volume_24h_usdt >= float(source.get("liquidity_tier_major_24h_usdt", SETTINGS.liquidity_tier_major_24h_usdt)):
        return LIQUIDITY_ARCHETYPE_MAJOR
    if observed_volume_24h_usdt >= float(source.get("liquidity_tier_mid_24h_usdt", SETTINGS.liquidity_tier_mid_24h_usdt)):
        return LIQUIDITY_ARCHETYPE_MID
    return LIQUIDITY_ARCHETYPE_SMALL


def resolve_archetype_floor_usdt(
    archetype: str,
    *,
    config: dict[str, Any] | None = None,
) -> float:
    source = config or {}
    floors = {
        LIQUIDITY_ARCHETYPE_MAJOR: float(source.get("liquidity_floor_major_24h_usdt", SETTINGS.liquidity_floor_major_24h_usdt)),
        LIQUIDITY_ARCHETYPE_MID: float(source.get("liquidity_floor_mid_24h_usdt", SETTINGS.liquidity_floor_mid_24h_usdt)),
        LIQUIDITY_ARCHETYPE_SMALL: float(source.get("liquidity_floor_small_24h_usdt", SETTINGS.liquidity_floor_small_24h_usdt)),
        LIQUIDITY_ARCHETYPE_MEME: float(source.get("liquidity_floor_meme_24h_usdt", SETTINGS.liquidity_floor_meme_24h_usdt)),
    }
    global_floor = float(source.get("multi_coin_liquidity_floor_usdt", SETTINGS.multi_coin_liquidity_floor_usdt))
    return max(
        floors.get(archetype, SETTINGS.liquidity_floor_small_24h_usdt),
        global_floor,
        float(SETTINGS.universe_min_24h_volume_usdt),
    )


def build_liquidity_policy(
    symbol: str,
    *,
    observed_volume_24h_usdt: float,
    interval: str = "1h",
    estimated_notional: Decimal | None = None,
    config: dict[str, Any] | None = None,
) -> LiquidityPolicy:
    archetype = infer_liquidity_archetype(
        symbol,
        observed_volume_24h_usdt=observed_volume_24h_usdt,
        config=config,
    )
    base_floor = resolve_archetype_floor_usdt(archetype, config=config)
    required_24h = base_floor
    if estimated_notional is not None:
        required_24h = max(required_24h, float(estimated_notional) * 100.0)

    interval_hours = resolve_interval_hours(interval)
    expected_interval = max(required_24h * (interval_hours / 24.0), 1.0)
    return LiquidityPolicy(
        archetype=archetype,
        base_daily_floor_usdt=base_floor,
        required_24h_volume_usdt=required_24h,
        discovery_floor_usdt=max(
            float(SETTINGS.universe_min_24h_volume_usdt),
            base_floor * _UNIVERSE_DISCOVERY_RATIO[archetype],
        ),
        interval_expected_volume_usdt=expected_interval,
        interval_soft_floor_usdt=max(expected_interval * _SCANNER_INTERVAL_SOFT_RATIO[archetype], 1.0),
        interval_hard_floor_usdt=max(expected_interval * _SCANNER_INTERVAL_HARD_RATIO[archetype], 1.0),
    )


def score_liquidity_depth(
    symbol: str,
    *,
    observed_volume_24h_usdt: float,
    config: dict[str, Any] | None = None,
) -> float:
    policy = build_liquidity_policy(
        symbol,
        observed_volume_24h_usdt=observed_volume_24h_usdt,
        config=config,
    )
    ratio = observed_volume_24h_usdt / max(policy.base_daily_floor_usdt, 1.0)
    if ratio >= 8.0:
        return 1.0
    if ratio >= 4.0:
        return 0.85 + ((ratio - 4.0) / 4.0) * 0.15
    if ratio >= 2.0:
        return 0.65 + ((ratio - 2.0) / 2.0) * 0.20
    if ratio >= 1.0:
        return 0.45 + (ratio - 1.0) * 0.20
    if ratio >= 0.75:
        return 0.30 + ((ratio - 0.75) / 0.25) * 0.15
    if ratio >= 0.50:
        return 0.15 + ((ratio - 0.50) / 0.25) * 0.15
    return 0.05 + max(ratio, 0.0) * 0.20
