from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.engine.reason_codes import REGIME_UNFAVORABLE, SETUP_TYPE_MISMATCH
from app.models.strategy import Strategy
from app.regime.types import MarketRegime
from app.risk.portfolio import get_correlation
from app.scanner.types import RankedSetup
from app.selector.selector import REGIME_AFFINITY

settings = get_settings()

STRATEGY_TYPE_ALIASES = {
    "hybrid_ai_composite": "hybrid_composite",
    "hybrid_composite": "hybrid_composite",
}


@dataclass(frozen=True)
class ScoringWeights:
    setup_fit: float
    regime_fit: float
    liquidity: float
    perf_memory: float
    vol_quality: float


@dataclass(frozen=True)
class StrategyScorerProfile:
    allowed_setups: set[str] | None
    favorable_regimes: set[MarketRegime] | None
    max_pick_count: int
    discovery_interval: str
    confirm_interval: str
    weights: ScoringWeights


@dataclass(frozen=True)
class StrategyCandidate:
    strategy_id: str
    strategy_name: str
    strategy_type: str
    symbol: str
    final_score: float
    regime: str
    setup_type: str
    recommended_strategy: str
    assignment_reason: str
    setup_fit_score: float
    regime_fit_score: float
    liquidity_score: float
    perf_memory_score: float
    vol_quality_score: float
    expected_rr_score: float
    liquidity_usdt: float
    market_quality_score: float
    reward_to_cost_ratio: float
    movement_quality: dict[str, Any]


@dataclass(frozen=True)
class StrategyRejection:
    strategy_id: str
    strategy_name: str
    strategy_type: str
    symbol: str
    reason_code: str
    reason_text: str
    setup_type: str | None = None
    regime: str | None = None


@dataclass(frozen=True)
class StrategyScoringResult:
    candidates: list[StrategyCandidate]
    rejections: list[StrategyRejection]


DEFAULT_WEIGHTS = ScoringWeights(
    setup_fit=0.35,
    regime_fit=0.25,
    liquidity=0.15,
    perf_memory=0.10,
    vol_quality=0.15,
)


STRATEGY_PROFILES = {
    "sma_crossover": StrategyScorerProfile(
        allowed_setups={"sma_crossover_proximity", "ema_trend_bullish", "ema_trend_bearish"},
        favorable_regimes={MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN},
        max_pick_count=4,
        discovery_interval="4h",
        confirm_interval="1h",
        weights=DEFAULT_WEIGHTS,
    ),
    "macd_momentum": StrategyScorerProfile(
        allowed_setups={
            "macd_crossover",
            "macd_momentum_rising",
            "macd_momentum_falling",
            "volume_breakout",
            "momentum_breakout_high",
            "adx_strong_trend",
        },
        favorable_regimes={MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN},
        max_pick_count=4,
        discovery_interval="4h",
        confirm_interval="1h",
        weights=DEFAULT_WEIGHTS,
    ),
    "rsi_mean_reversion": StrategyScorerProfile(
        allowed_setups={
            "rsi_oversold",
            "rsi_overbought",
            "rsi_divergence_bullish",
            "rsi_divergence_bearish",
            "momentum_breakout_low",
            "adx_strong_trend",
        },
        favorable_regimes={MarketRegime.RANGING, MarketRegime.HIGH_VOLATILITY},
        max_pick_count=6,
        discovery_interval="1h",
        confirm_interval="15m",
        weights=DEFAULT_WEIGHTS,
    ),
    "bollinger_bounce": StrategyScorerProfile(
        allowed_setups={"bb_squeeze", "bb_lower_touch", "bb_upper_touch"},
        favorable_regimes={MarketRegime.RANGING, MarketRegime.HIGH_VOLATILITY},
        max_pick_count=5,
        discovery_interval="1h",
        confirm_interval="15m",
        weights=DEFAULT_WEIGHTS,
    ),
    "hybrid_composite": StrategyScorerProfile(
        allowed_setups=None,
        favorable_regimes=None,
        max_pick_count=2,
        discovery_interval="4h",
        confirm_interval="1h",
        weights=ScoringWeights(
            setup_fit=0.40,
            regime_fit=0.20,
            liquidity=0.15,
            perf_memory=0.10,
            vol_quality=0.15,
        ),
    ),
}
STRATEGY_PROFILES["hybrid_ai_composite"] = STRATEGY_PROFILES["hybrid_composite"]


def normalize_strategy_type(value: str | None) -> str:
    normalized = (value or "sma_crossover").strip().lower().replace("-", "_")
    return STRATEGY_TYPE_ALIASES.get(normalized, normalized)


def resolve_strategy_type(strategy: Strategy) -> str:
    config = strategy.config_json or {}
    strategy_type = str(
        strategy.ai_strategy_key
        or config.get("strategy_type")
        or config.get("base_strategy_type")
        or "sma_crossover"
    )
    if strategy_type == "ai":
        strategy_type = str(config.get("base_strategy_type") or "sma_crossover")
    return normalize_strategy_type(strategy_type)


def get_strategy_profile(strategy_type: str | None) -> StrategyScorerProfile | None:
    return STRATEGY_PROFILES.get(normalize_strategy_type(strategy_type))


def score_universe_for_strategy(
    strategy: Strategy,
    profile: StrategyScorerProfile,
    scanner_results: dict[str, list[RankedSetup]],
    regime_cache: dict[str, MarketRegime] | None = None,
    *,
    max_pick_count: int | None = None,
) -> list[StrategyCandidate]:
    return evaluate_universe_for_strategy(
        strategy,
        profile,
        scanner_results,
        regime_cache,
        max_pick_count=max_pick_count,
    ).candidates


def evaluate_universe_for_strategy(
    strategy: Strategy,
    profile: StrategyScorerProfile,
    scanner_results: dict[str, list[RankedSetup]],
    regime_cache: dict[str, MarketRegime] | None = None,
    *,
    max_pick_count: int | None = None,
) -> StrategyScoringResult:
    strategy_type = resolve_strategy_type(strategy)
    results: list[StrategyCandidate] = []
    rejections: list[StrategyRejection] = []
    liquidity_floor = max(float(settings.multi_coin_liquidity_floor_usdt), 1.0)
    effective_max = max_pick_count if max_pick_count is not None else profile.max_pick_count

    for symbol, setups in scanner_results.items():
        eligible = [s for s in setups if s.entry_eligible]
        if profile.allowed_setups is not None:
            eligible = [setup for setup in eligible if setup.setup_type in profile.allowed_setups]
        if not eligible:
            rejections.append(
                StrategyRejection(
                    strategy_id=strategy.id,
                    strategy_name=strategy.name,
                    strategy_type=strategy_type,
                    symbol=symbol,
                    reason_code=SETUP_TYPE_MISMATCH,
                    reason_text="No entry-eligible setup matched this strategy profile",
                )
            )
            continue

        best_setup = max(eligible, key=lambda item: item.score)
        regime = (regime_cache or {}).get(symbol) or _parse_regime(best_setup.regime)
        regime_fit = _resolve_regime_fit(regime, strategy_type)
        if _is_regime_unfavorable(profile, regime, regime_fit):
            rejections.append(
                StrategyRejection(
                    strategy_id=strategy.id,
                    strategy_name=strategy.name,
                    strategy_type=strategy_type,
                    symbol=symbol,
                    reason_code=REGIME_UNFAVORABLE,
                    reason_text=f"Regime {best_setup.regime} is unfavorable for {strategy_type}",
                    setup_type=best_setup.setup_type,
                    regime=best_setup.regime,
                )
            )
            continue

        liquidity_score = min(best_setup.liquidity_usdt / (liquidity_floor * 4.0), 1.0)
        perf_memory_score = 0.5
        vol_quality_score = _clamp01(best_setup.volatility_quality_score)
        expected_rr_score = _clamp01(best_setup.reward_to_cost_ratio / 3.0)

        # Blend family quality into setup fit when available
        setup_fit_base = best_setup.score
        if best_setup.symbol_quality_score > 0:
            setup_fit_base = best_setup.score * 0.6 + best_setup.symbol_quality_score * 0.25 + best_setup.execution_quality_score * 0.15

        final_score = (
            setup_fit_base * profile.weights.setup_fit
            + regime_fit * profile.weights.regime_fit
            + liquidity_score * profile.weights.liquidity
            + perf_memory_score * profile.weights.perf_memory
            + vol_quality_score * profile.weights.vol_quality
        )
        results.append(
            StrategyCandidate(
                strategy_id=strategy.id,
                strategy_name=strategy.name,
                strategy_type=strategy_type,
                symbol=symbol,
                final_score=round(final_score, 4),
                regime=best_setup.regime,
                setup_type=best_setup.setup_type,
                recommended_strategy=normalize_strategy_type(best_setup.recommended_strategy),
                assignment_reason=best_setup.reason,
                setup_fit_score=round(setup_fit_base, 4),
                regime_fit_score=round(regime_fit, 4),
                liquidity_score=round(liquidity_score, 4),
                perf_memory_score=round(perf_memory_score, 4),
                vol_quality_score=round(vol_quality_score, 4),
                expected_rr_score=round(expected_rr_score, 4),
                liquidity_usdt=round(best_setup.liquidity_usdt, 2),
                market_quality_score=round(best_setup.market_quality_score, 4),
                reward_to_cost_ratio=round(best_setup.reward_to_cost_ratio, 4),
                movement_quality=dict(best_setup.movement_quality),
            )
        )

    results.sort(key=lambda item: item.final_score, reverse=True)
    selected = _apply_correlation_penalty(results, max(1, effective_max))
    return StrategyScoringResult(candidates=selected, rejections=rejections)


# Static behavior-cluster map for common pairs.
# Symbols in the same cluster receive a crowding penalty when co-selected.
BEHAVIOR_CLUSTER: dict[str, str] = {
    "BTCUSDT": "btc",
    "ETHUSDT": "eth_l1",
    "SOLUSDT": "alt_l1",
    "BNBUSDT": "exchange",
    "ADAUSDT": "alt_l1",
    "DOTUSDT": "alt_l1",
    "AVAXUSDT": "alt_l1",
    "MATICUSDT": "alt_l1",
    "LINKUSDT": "oracle",
    "ATOMUSDT": "cosmos",
    "NEARUSDT": "alt_l1",
    "APTUSDT": "alt_l1",
    "ARBUSDT": "eth_l2",
    "OPUSDT": "eth_l2",
    "SUIUSDT": "alt_l1",
    "DOGEUSDT": "meme",
    "SHIBUSDT": "meme",
    "PEPEUSDT": "meme",
}

_CLUSTER_CROWDING_FACTORS = [1.0, 0.85, 0.70, 0.55]  # 1st, 2nd, 3rd, 4th in same cluster


def _apply_correlation_penalty(
    candidates: list[StrategyCandidate],
    max_pick_count: int,
) -> list[StrategyCandidate]:
    selected: list[StrategyCandidate] = []
    remaining = candidates[:]
    cluster_counts: dict[str, int] = {}

    while remaining and len(selected) < max_pick_count:
        best_idx = 0
        best_score = -1.0
        for idx, candidate in enumerate(remaining):
            adjusted_score = candidate.final_score
            # Correlation penalty
            if selected:
                max_corr = max(get_correlation(candidate.symbol, chosen.symbol) for chosen in selected)
                adjusted_score *= max(0.25, 1.0 - (0.35 * max_corr))
            # Behavior-cluster crowding penalty
            cluster = BEHAVIOR_CLUSTER.get(candidate.symbol)
            if cluster and cluster in cluster_counts:
                count = cluster_counts[cluster]
                factor = _CLUSTER_CROWDING_FACTORS[min(count, len(_CLUSTER_CROWDING_FACTORS) - 1)]
                adjusted_score *= factor
            if adjusted_score > best_score:
                best_score = adjusted_score
                best_idx = idx
        chosen = remaining.pop(best_idx)
        # Track cluster
        cluster = BEHAVIOR_CLUSTER.get(chosen.symbol)
        if cluster:
            cluster_counts[cluster] = cluster_counts.get(cluster, 0) + 1
        if best_score != chosen.final_score:
            chosen = StrategyCandidate(
                **{
                    **chosen.__dict__,
                    "final_score": round(best_score, 4),
                }
            )
        selected.append(chosen)
    return selected


def _resolve_regime_fit(regime: MarketRegime | None, strategy_type: str) -> float:
    if regime is None:
        return 0.5
    affinity_map = REGIME_AFFINITY.get(regime, {})
    return float(affinity_map.get(strategy_type, affinity_map.get(normalize_strategy_type(strategy_type), 0.5)))


def _parse_regime(value: str | None) -> MarketRegime | None:
    if not value:
        return None
    try:
        return MarketRegime(value)
    except ValueError:
        return None


def _is_regime_unfavorable(
    profile: StrategyScorerProfile,
    regime: MarketRegime | None,
    regime_fit: float,
) -> bool:
    if regime is None or profile.favorable_regimes is None:
        return False
    return regime not in profile.favorable_regimes and regime_fit < 0.5


def _clamp01(value: float) -> float:
    return max(0.0, min(value, 1.0))
