"""Opportunity scanner — scans multiple symbols for trading setups."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.config import DEFAULT_SCAN_UNIVERSE, get_settings
from app.engine.reason_codes import (
    LIQUIDITY_TOO_LOW,
    MARKET_DATA_INSUFFICIENT,
    NO_QUALIFYING_SETUP,
    QUALIFIED_SETUP,
    SETUP_GAP_ONLY,
    SETUP_NO_ABSOLUTE_EXPANSION,
    SETUP_RANGE_TOO_SMALL,
    SETUP_SCORE_TOO_LOW,
    SETUP_SLOPE_TOO_WEAK,
    SETUP_STRUCTURE_TOO_WEAK,
)
from app.engine.tradability import (
    build_tradability_metrics,
    evaluate_movement_quality,
    evaluate_symbol_tradability,
)
from app.engine.liquidity_policy import build_liquidity_policy
from app.market.data_store import DataStore
from app.market.indicators import compute_indicators
from app.regime.classifier import RegimeClassifier
from app.regime.types import DetailedRegime, MarketRegime, RegimeResult
from app.risk.portfolio import get_correlation
from app.scanner.families import (
    SETUP_TO_FAMILY,
    resolve_family,
    validate_setup_family,
)
from app.scanner.relative_strength import get_relative_strength
from app.scanner.types import RankedSetup, RankedSymbol, ScanResult, SetupAuditNote
from app.scanner.universe_selector import UniverseSelector
from app.selector.selector import REGIME_AFFINITY

logger = logging.getLogger(__name__)
settings = get_settings()

DEFAULT_SYMBOLS = list(DEFAULT_SCAN_UNIVERSE)
MIN_SETUP_SCORE = 0.30
MIN_CANDLES_FOR_SCAN = 50


class OpportunityScanner:
    """Scans multiple symbols for trading setups and ranks them."""

    def __init__(self, symbols: list[str] | None = None):
        self.symbols = symbols or DEFAULT_SYMBOLS
        self._symbols_from_dynamic: bool = symbols is None
        self.regime_classifier = RegimeClassifier()
        self._last_rank_audit: list[dict[str, Any]] = []
        self._last_regime_cache: dict[str, MarketRegime] = {}

    async def resolve_symbols(
        self,
        *,
        retained_symbols: set[str] | None = None,
    ) -> list[str]:
        if not self._symbols_from_dynamic:
            return self.symbols
        if not settings.dynamic_universe_enabled:
            return self.symbols

        selector = UniverseSelector.get_instance()
        dynamic_symbols = await selector.get_active_universe(retained_symbols=retained_symbols)
        if dynamic_symbols:
            self.symbols = dynamic_symbols
            logger.info("scanner: using dynamic universe (%d symbols)", len(dynamic_symbols))
        else:
            logger.warning("scanner: dynamic universe returned empty, using defaults")
        return self.symbols

    def scan(
        self,
        interval: str = "1h",
        max_results: int = 5,
    ) -> ScanResult:
        store = DataStore.get_instance()
        opportunities: list[RankedSetup] = []
        symbols_with_data = 0
        symbols_no_data: list[str] = []
        symbols_no_setup: list[str] = []
        overall_regime = "unknown"

        for symbol in self.symbols:
            candles = store.get_candles(symbol, interval, 200)
            if len(candles) < MIN_CANDLES_FOR_SCAN:
                symbols_no_data.append(f"{symbol}({len(candles)})")
                continue

            symbols_with_data += 1
            closes = [c.close for c in candles]
            highs = [c.high for c in candles]
            lows = [c.low for c in candles]
            volumes = [c.volume for c in candles]
            indicators = compute_indicators(closes, highs=highs, lows=lows, volumes=volumes)
            tradability = evaluate_symbol_tradability(
                symbol=symbol,
                closes=closes,
                highs=highs,
                lows=lows,
                volumes=volumes,
                volume_24h_usdt=self._estimate_liquidity_usdt(candles, window=24),
                indicators=indicators,
            )
            if not tradability.passed:
                symbols_no_setup.append(symbol)
                continue
            regime_result = self.regime_classifier.classify_full(indicators)
            if symbol == "BTCUSDT":
                overall_regime = regime_result.regime.value

            setups, _ = self._detect_setups(
                symbol,
                indicators,
                regime_result.regime,
                closes=closes,
                highs=highs,
                lows=lows,
                volumes=volumes,
                regime_result=regime_result,
            )
            if not setups:
                symbols_no_setup.append(symbol)
            opportunities.extend(setups)

        if symbols_no_data:
            logger.warning(
                "scanner: %d/%d symbols skipped (insufficient data): %s",
                len(symbols_no_data),
                len(self.symbols),
                ", ".join(symbols_no_data[:10]),
            )
        if symbols_no_setup:
            logger.info(
                "scanner: %d symbols had data but no setup detected: %s",
                len(symbols_no_setup),
                ", ".join(symbols_no_setup[:10]),
            )
        logger.info(
            "scanner: %d symbols scanned, %d setups found, regime=%s",
            symbols_with_data,
            len(opportunities),
            overall_regime,
        )

        opportunities.sort(key=lambda s: s.score, reverse=True)
        return ScanResult(
            scanned_at=datetime.now(timezone.utc).isoformat(),
            symbols_scanned=symbols_with_data,
            regime=overall_regime,
            opportunities=opportunities[:max_results],
        )

    def rank_symbols(
        self,
        interval: str = "1h",
        max_results: int = 5,
        *,
        liquidity_floor_usdt: float | None = None,
    ) -> list[RankedSymbol]:
        store = DataStore.get_instance()
        candidates: list[RankedSymbol] = []
        min_liquidity = float(
            liquidity_floor_usdt if liquidity_floor_usdt is not None else settings.multi_coin_liquidity_floor_usdt
        )

        skipped_data: list[str] = []
        skipped_setup: list[str] = []
        skipped_liquidity: list[str] = []
        audit_rows: list[dict[str, Any]] = []

        for symbol in self.symbols:
            candles = store.get_candles(symbol, interval, 200)
            volume_1h_usdt = round(
                self._estimate_one_hour_volume_usdt(candles, interval),
                2,
            )
            daily_liquidity_usdt = round(
                self._estimate_liquidity_usdt(candles, window=24),
                2,
            )
            liquidity_policy = build_liquidity_policy(
                symbol,
                observed_volume_24h_usdt=daily_liquidity_usdt,
                interval=interval,
                config={"multi_coin_liquidity_floor_usdt": min_liquidity},
            )
            threshold_volume_1h_usdt = round(liquidity_policy.interval_hard_floor_usdt, 2)
            if len(candles) < MIN_CANDLES_FOR_SCAN:
                skipped_data.append(f"{symbol}({len(candles)})")
                audit_rows.append({
                    "symbol": symbol,
                    "status": "skipped",
                    "reason_code": MARKET_DATA_INSUFFICIENT,
                    "reason_text": "Insufficient candle history for scan",
                    "setup_type": None,
                    "movement_quality": {},
                    "score": 0.0,
                    "volume_1h_usdt": volume_1h_usdt,
                    "threshold_volume_1h_usdt": threshold_volume_1h_usdt,
                })
                continue

            closes = [c.close for c in candles]
            highs = [c.high for c in candles]
            lows = [c.low for c in candles]
            volumes = [c.volume for c in candles]
            indicators = compute_indicators(closes, highs=highs, lows=lows, volumes=volumes)
            tradability = evaluate_symbol_tradability(
                symbol=symbol,
                closes=closes,
                highs=highs,
                lows=lows,
                volumes=volumes,
                volume_24h_usdt=daily_liquidity_usdt,
                indicators=indicators,
                config={"multi_coin_liquidity_floor_usdt": min_liquidity},
            )
            if not tradability.passed:
                audit_rows.append({
                    "symbol": symbol,
                    "status": "rejected",
                    "reason_code": tradability.reason_codes[0] if tradability.reason_codes else None,
                    "reason_text": tradability.reason_text,
                    "setup_type": None,
                    "movement_quality": tradability.metrics.to_dict(),
                    "score": 0.0,
                    "volume_1h_usdt": volume_1h_usdt,
                    "threshold_volume_1h_usdt": threshold_volume_1h_usdt,
                })
                continue
            regime_result = self.regime_classifier.classify_full(indicators)
            setups, audits = self._detect_setups(
                symbol,
                indicators,
                regime_result.regime,
                closes=closes,
                highs=highs,
                lows=lows,
                volumes=volumes,
                regime_result=regime_result,
            )
            if not setups:
                skipped_setup.append(symbol)
                first_rejection = next((audit for audit in audits if audit.status == "rejected"), None)
                audit_rows.append({
                    "symbol": symbol,
                    "status": "rejected",
                    "reason_code": first_rejection.reason_code if first_rejection else NO_QUALIFYING_SETUP,
                    "reason_text": first_rejection.reason_text if first_rejection else "No setup passed movement-quality checks",
                    "setup_type": first_rejection.setup_type if first_rejection else None,
                    "movement_quality": first_rejection.metrics if first_rejection else {},
                    "score": 0.0,
                    "volume_1h_usdt": volume_1h_usdt,
                    "threshold_volume_1h_usdt": threshold_volume_1h_usdt,
                })
                continue

            # Filter to entry-eligible setups for ranking (long-only engine)
            eligible_setups = [s for s in setups if s.entry_eligible]
            if not eligible_setups:
                skipped_setup.append(symbol)
                audit_rows.append({
                    "symbol": symbol,
                    "status": "rejected",
                    "reason_code": NO_QUALIFYING_SETUP,
                    "reason_text": "No entry-eligible (long) setups found",
                    "setup_type": setups[0].setup_type if setups else None,
                    "movement_quality": setups[0].movement_quality if setups else {},
                    "score": setups[0].score if setups else 0.0,
                    "volume_1h_usdt": volume_1h_usdt,
                    "threshold_volume_1h_usdt": threshold_volume_1h_usdt,
                })
                continue
            best_setup = max(eligible_setups, key=lambda setup: setup.score)
            if volume_1h_usdt < liquidity_policy.interval_hard_floor_usdt:
                skipped_liquidity.append(f"{symbol}(${volume_1h_usdt:,.0f}/h)")
                audit_rows.append({
                    "symbol": symbol,
                    "status": "rejected",
                    "reason_code": LIQUIDITY_TOO_LOW,
                    "reason_text": (
                        f"{liquidity_policy.archetype} interval liquidity ${volume_1h_usdt:,.0f}/h below "
                        f"severe floor ${liquidity_policy.interval_hard_floor_usdt:,.0f}/h"
                    ),
                    "setup_type": best_setup.setup_type,
                    "movement_quality": best_setup.movement_quality,
                    "score": best_setup.score,
                    "volume_1h_usdt": volume_1h_usdt,
                    "threshold_volume_1h_usdt": threshold_volume_1h_usdt,
                })
                continue
            liquidity_penalty = 0.0
            if volume_1h_usdt < liquidity_policy.interval_soft_floor_usdt:
                liquidity_penalty = min(
                    0.15,
                    0.03
                    + (
                        (liquidity_policy.interval_soft_floor_usdt - volume_1h_usdt)
                        / max(liquidity_policy.interval_soft_floor_usdt, 1.0)
                    ) * 0.12,
                )

            advisory_penalty = min(0.12, 0.03 * len(tradability.advisory_reason_codes))

            # Contradiction penalty: bullish + bearish eligible families present
            has_buy = any(s.signal == "BUY" for s in setups)
            has_sell = any(s.signal == "SELL" for s in setups)
            contradiction_penalty = 0.10 if (has_buy and has_sell) else 0.0

            # Exhaustion penalty from regime
            exhaustion_penalty = 0.08 if regime_result.exhaustion_score >= 0.5 else 0.0

            # Net quality score: weighted blend of family quality metrics
            regime_affinity = REGIME_AFFINITY.get(regime_result.regime, {}).get(best_setup.recommended_strategy, 0.5)
            liquidity_score = min(
                daily_liquidity_usdt / max(liquidity_policy.required_24h_volume_usdt * 4.0, 1.0),
                1.0,
            )
            net_quality = (
                best_setup.room_to_move_score * 0.25
                + best_setup.execution_quality_score * 0.20
                + best_setup.freshness_score * 0.15
                + best_setup.symbol_quality_score * 0.15
                + best_setup.score * 0.15
                + regime_affinity * 0.10
            ) - contradiction_penalty - exhaustion_penalty - advisory_penalty - liquidity_penalty

            final_score = max(0.0, net_quality * 0.70 + best_setup.score * 0.20 + liquidity_score * 0.10)
            candidates.append(
                RankedSymbol(
                    symbol=symbol,
                    score=final_score,
                    regime=regime_result.regime.value,
                    setup_type=best_setup.setup_type,
                    recommended_strategy=best_setup.recommended_strategy,
                    reason=best_setup.reason,
                    liquidity_usdt=daily_liquidity_usdt,
                    indicators=best_setup.indicators,
                    reason_code=best_setup.reason_code,
                    reason_codes=best_setup.reason_codes,
                    reason_text=best_setup.reason_text or best_setup.reason,
                    movement_quality=best_setup.movement_quality,
                    family=best_setup.family,
                    entry_eligible=True,
                    net_quality_score=round(net_quality, 4),
                    contradiction_penalty=round(contradiction_penalty, 4),
                    exhaustion_penalty=round(exhaustion_penalty, 4),
                    detailed_regime=best_setup.detailed_regime,
                )
            )
            audit_rows.append({
                "symbol": symbol,
                "status": "qualified",
                "reason_code": best_setup.reason_code,
                "reason_text": best_setup.reason_text or best_setup.reason,
                "setup_type": best_setup.setup_type,
                "movement_quality": best_setup.movement_quality,
                "score": best_setup.score,
                "volume_1h_usdt": volume_1h_usdt,
                "threshold_volume_1h_usdt": threshold_volume_1h_usdt,
                "family": best_setup.family,
                "net_quality_score": round(net_quality, 4),
                "advisory_penalty": round(advisory_penalty, 4),
                "liquidity_penalty": round(liquidity_penalty, 4),
            })

        if skipped_data:
            logger.warning("rank_symbols: %d symbols skipped (no data): %s", len(skipped_data), ", ".join(skipped_data[:10]))
        if skipped_setup:
            logger.info("rank_symbols: %d symbols skipped (no setup): %s", len(skipped_setup), ", ".join(skipped_setup[:10]))
        if skipped_liquidity:
            logger.info(
                "rank_symbols: %d symbols skipped (low liquidity, floor=$%s): %s",
                len(skipped_liquidity),
                f"{min_liquidity:,.0f}",
                ", ".join(skipped_liquidity[:10]),
            )
        logger.info("rank_symbols: %d candidates from %d symbols scanned", len(candidates), len(self.symbols))

        candidates.sort(key=lambda item: item.score, reverse=True)

        selected: list[RankedSymbol] = []
        remaining = candidates[:]
        while remaining and len(selected) < max_results:
            best_idx = 0
            best_score = -1.0
            for idx, candidate in enumerate(remaining):
                adjusted_score = candidate.score
                if selected:
                    max_corr = max(get_correlation(candidate.symbol, chosen.symbol) for chosen in selected)
                    adjusted_score *= max(0.25, 1.0 - (0.35 * max_corr))
                if adjusted_score > best_score:
                    best_score = adjusted_score
                    best_idx = idx

            selected_candidate = remaining.pop(best_idx)
            selected.append(
                RankedSymbol(
                    symbol=selected_candidate.symbol,
                    score=round(best_score, 4),
                    regime=selected_candidate.regime,
                    setup_type=selected_candidate.setup_type,
                    recommended_strategy=selected_candidate.recommended_strategy,
                    reason=selected_candidate.reason,
                    liquidity_usdt=selected_candidate.liquidity_usdt,
                    indicators=selected_candidate.indicators,
                    reason_code=selected_candidate.reason_code,
                    reason_codes=selected_candidate.reason_codes,
                    reason_text=selected_candidate.reason_text,
                    movement_quality=selected_candidate.movement_quality,
                    family=selected_candidate.family,
                    entry_eligible=selected_candidate.entry_eligible,
                    net_quality_score=selected_candidate.net_quality_score,
                    contradiction_penalty=selected_candidate.contradiction_penalty,
                    exhaustion_penalty=selected_candidate.exhaustion_penalty,
                    detailed_regime=selected_candidate.detailed_regime,
                )
            )

        self._last_rank_audit = audit_rows
        return selected

    def get_last_rank_audit(self) -> list[dict[str, Any]]:
        """Return the raw audit rows from the last rank_symbols call."""
        return self._last_rank_audit

    def get_rank_funnel_stats(self) -> dict[str, int]:
        """Derive funnel breakdown from the last rank_symbols audit."""
        stats = {"no_data": 0, "tradability_rejected": 0, "no_setup": 0, "low_liquidity": 0, "qualified": 0}
        for row in self._last_rank_audit:
            if row["status"] == "qualified":
                stats["qualified"] += 1
            elif row.get("reason_code") == MARKET_DATA_INSUFFICIENT:
                stats["no_data"] += 1
            elif row.get("reason_code") == LIQUIDITY_TOO_LOW:
                stats["low_liquidity"] += 1
            elif row.get("reason_code") == NO_QUALIFYING_SETUP:
                stats["no_setup"] += 1
            else:
                stats["tradability_rejected"] += 1
        return stats

    def scan_all_setups_for_universe(
        self,
        interval: str = "1h",
    ) -> dict[str, list[RankedSetup]]:
        store = DataStore.get_instance()
        audit_rows: list[dict[str, Any]] = []
        all_results: dict[str, list[RankedSetup]] = {}
        self._last_regime_cache = {}

        for symbol in self.symbols:
            candles = store.get_candles(symbol, interval, 200)
            if len(candles) < MIN_CANDLES_FOR_SCAN:
                audit_rows.append({
                    "symbol": symbol,
                    "status": "skipped",
                    "reason_code": MARKET_DATA_INSUFFICIENT,
                    "reason_text": "Insufficient candle history for scan",
                    "setup_type": None,
                    "movement_quality": {},
                    "score": 0.0,
                })
                all_results[symbol] = []
                continue

            closes = [c.close for c in candles]
            highs = [c.high for c in candles]
            lows = [c.low for c in candles]
            volumes = [c.volume for c in candles]
            indicators = compute_indicators(closes, highs=highs, lows=lows, volumes=volumes)
            tradability = evaluate_symbol_tradability(
                symbol=symbol,
                closes=closes,
                highs=highs,
                lows=lows,
                volumes=volumes,
                volume_24h_usdt=self._estimate_liquidity_usdt(candles, window=24),
                indicators=indicators,
            )
            if not tradability.passed:
                audit_rows.append({
                    "symbol": symbol,
                    "status": "rejected",
                    "reason_code": tradability.reason_codes[0] if tradability.reason_codes else None,
                    "reason_text": tradability.reason_text,
                    "setup_type": None,
                    "movement_quality": tradability.metrics.to_dict(),
                    "score": 0.0,
                })
                all_results[symbol] = []
                continue

            regime_result = self.regime_classifier.classify_full(indicators)
            self._last_regime_cache[symbol] = regime_result.regime
            setups, audits = self._detect_setups(
                symbol,
                indicators,
                regime_result.regime,
                closes=closes,
                highs=highs,
                lows=lows,
                volumes=volumes,
                regime_result=regime_result,
            )
            setups.sort(key=lambda item: item.score, reverse=True)
            all_results[symbol] = setups
            primary = next((audit for audit in audits if audit.status == "qualified"), None)
            if primary is None:
                primary = next((audit for audit in audits if audit.status == "rejected"), None)
            audit_rows.append({
                "symbol": symbol,
                "status": primary.status if primary is not None else "rejected",
                "reason_code": primary.reason_code if primary is not None else NO_QUALIFYING_SETUP,
                "reason_text": primary.reason_text if primary is not None else "No qualifying setup detected",
                "setup_type": primary.setup_type if primary is not None else None,
                "movement_quality": primary.metrics if primary is not None else {},
                "score": setups[0].score if setups else 0.0,
            })

        self._last_rank_audit = audit_rows
        return all_results

    def get_last_rank_audit(self) -> list[dict[str, Any]]:
        return list(self._last_rank_audit)

    def get_last_regime_cache(self) -> dict[str, MarketRegime]:
        return dict(self._last_regime_cache)

    def _detect_setups(
        self,
        symbol: str,
        indicators: dict[str, Any],
        regime: MarketRegime,
        closes: list[float] | None = None,
        highs: list[float] | None = None,
        lows: list[float] | None = None,
        volumes: list[float] | None = None,
        regime_result: RegimeResult | None = None,
    ) -> tuple[list[RankedSetup], list[SetupAuditNote]]:
        setups: list[RankedSetup] = []
        audits: list[SetupAuditNote] = []
        closes = closes or []
        highs = highs or []
        lows = lows or []
        volumes = volumes or []

        recent_quote_volumes = [close * volume for close, volume in zip(closes[-24:], volumes[-24:])]
        volume_24h_usdt = sum(recent_quote_volumes)
        tradability_metrics = build_tradability_metrics(
            symbol=symbol,
            closes=closes,
            highs=highs,
            lows=lows,
            volumes=volumes,
            volume_24h_usdt=volume_24h_usdt,
            indicators=indicators,
        )

        rsi_values = indicators.get("rsi", [])
        latest_rsi = rsi_values[-1] if rsi_values else None

        bb = indicators.get("bollinger_bands", ([], [], []))
        bb_upper, bb_middle, bb_lower = bb if len(bb) == 3 else ([], [], [])

        volume_ratio_values = indicators.get("volume_ratio", [])
        latest_volume_ratio = volume_ratio_values[-1] if volume_ratio_values else None

        sma_short = indicators.get("sma_short", [])
        sma_long = indicators.get("sma_long", [])

        latest_close = indicators.get("latest_close")
        previous_close = indicators.get("previous_close")

        macd_data = indicators.get("macd", ([], [], []))
        macd_line, macd_signal, macd_hist = macd_data if isinstance(macd_data, tuple) and len(macd_data) == 3 else ([], [], [])

        adx_values = indicators.get("adx", [])
        latest_adx = adx_values[-1] if adx_values else None

        ema_12 = indicators.get("ema_12", [])
        ema_26 = indicators.get("ema_26", [])
        price_for_volatility = float(latest_close or closes[-1]) if (latest_close or closes) else 0.0
        volatility_quality_score = (
            UniverseSelector._score_volatility_quality(symbol, price_for_volatility, DataStore.get_instance())
            if price_for_volatility > 0
            else 0.3
        )

        def reject(setup_type: str, reason_code: str, reason_text: str, metrics: dict[str, Any] | None = None) -> None:
            audits.append(
                SetupAuditNote(
                    symbol=symbol,
                    setup_type=setup_type,
                    status="rejected",
                    reason_code=reason_code,
                    reason_codes=[reason_code],
                    reason_text=reason_text,
                    metrics=metrics or {},
                )
            )

        _detailed_regime = regime_result.detailed_regime if regime_result else None
        _exhaustion = regime_result.exhaustion_score if regime_result else 0.0

        def qualify(
            *,
            setup_type: str,
            signal: str,
            score: float,
            recommended_strategy: str,
            reason: str,
            indicators_payload: dict[str, Any],
            require_volume: bool = True,
            extra_checks: list[tuple[bool, str, str]] | None = None,
        ) -> None:
            direction = "BUY" if signal == "BUY" else "SELL"
            movement = evaluate_movement_quality(direction=direction, metrics=tradability_metrics, require_volume=require_volume)
            if not movement.passed:
                reject(setup_type, movement.reason_code or SETUP_NO_ABSOLUTE_EXPANSION, movement.reason_text, movement.metrics)
                return
            for passed, reason_code, reason_text in extra_checks or []:
                if not passed:
                    reject(setup_type, reason_code, reason_text, movement.metrics)
                    return
            if score < MIN_SETUP_SCORE:
                reject(setup_type, SETUP_SCORE_TOO_LOW, "Setup score below minimum threshold", movement.metrics)
                return

            # Family validation (additive — does not block if family unknown)
            family_str = ""
            entry_eligible = True
            sym_quality = 0.0
            exec_quality = 0.0
            room_score = 0.0
            fv = validate_setup_family(
                setup_type=setup_type,
                signal=signal,
                indicators=indicators,
                tradability_metrics=tradability_metrics,
                detailed_regime=_detailed_regime,
                exhaustion_score=_exhaustion,
            )
            if fv is not None:
                family_str = fv.family.value
                entry_eligible = fv.entry_eligible
                sym_quality = fv.symbol_quality_score
                exec_quality = fv.execution_quality_score
                room_score = fv.room_to_move_score
                if not fv.passed:
                    reject(setup_type, "FAMILY_VALIDATION_FAILED", fv.rejection_reason or "Family validation failed", movement.metrics)
                    return

            setups.append(
                RankedSetup(
                    symbol=symbol,
                    score=score,
                    setup_type=setup_type,
                    signal=signal,
                    regime=regime.value,
                    recommended_strategy=recommended_strategy,
                    reason=reason,
                    indicators=indicators_payload,
                    reason_code=QUALIFIED_SETUP,
                    reason_codes=[QUALIFIED_SETUP],
                    reason_text=reason,
                    movement_quality=movement.to_dict(),
                    liquidity_usdt=round(volume_24h_usdt, 2),
                    market_quality_score=round(tradability_metrics.market_quality_score, 4),
                    reward_to_cost_ratio=round(tradability_metrics.reward_to_cost_ratio, 4),
                    volatility_quality_score=round(volatility_quality_score, 4),
                    family=family_str,
                    entry_eligible=entry_eligible,
                    symbol_quality_score=sym_quality,
                    execution_quality_score=exec_quality,
                    room_to_move_score=room_score,
                    detailed_regime=_detailed_regime.value if _detailed_regime else "",
                )
            )
            audits.append(
                SetupAuditNote(
                    symbol=symbol,
                    setup_type=setup_type,
                    status="qualified",
                    reason_code=QUALIFIED_SETUP,
                    reason_codes=[QUALIFIED_SETUP],
                    reason_text=reason,
                    metrics=movement.metrics,
                )
            )

        if latest_rsi is not None and latest_rsi < 35:
            strength = max(0, (35 - latest_rsi) / 35)
            regime_align = 1.0 if regime == MarketRegime.RANGING else 0.6
            vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
            score = self._setup_score(strength, regime_align, vol_confirm, 0.5, symbol)
            qualify(
                setup_type="rsi_oversold",
                signal="BUY",
                score=score,
                recommended_strategy="rsi_mean_reversion",
                reason=f"RSI oversold at {latest_rsi:.1f}",
                indicators_payload={"rsi": round(latest_rsi, 2), "volume_ratio": round(latest_volume_ratio or 0, 2)},
                require_volume=False,
            )

        if latest_rsi is not None and latest_rsi > 65:
            strength = max(0, (latest_rsi - 65) / 35)
            regime_align = 1.0 if regime == MarketRegime.RANGING else 0.6
            vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
            score = self._setup_score(strength, regime_align, vol_confirm, 0.5, symbol)
            qualify(
                setup_type="rsi_overbought",
                signal="SELL",
                score=score,
                recommended_strategy="rsi_mean_reversion",
                reason=f"RSI overbought at {latest_rsi:.1f}",
                indicators_payload={"rsi": round(latest_rsi, 2)},
                require_volume=False,
            )

        if bb_upper and bb_middle and bb_lower and bb_middle[-1] != 0 and len(bb_upper) >= 50:
            current_width = (bb_upper[-1] - bb_lower[-1]) / bb_middle[-1]
            widths = [
                (bb_upper[i] - bb_lower[i]) / bb_middle[i]
                for i in range(max(0, len(bb_upper) - 50), len(bb_upper))
                if bb_middle[i] != 0
            ]
            pct_rank = sum(1 for w in widths if w > current_width) / len(widths)
            if pct_rank > 0.70:
                strength = pct_rank
                vol_confirm = min(latest_volume_ratio / 1.2, 1.0) if latest_volume_ratio and latest_volume_ratio > 1.2 else 0.4
                score = self._setup_score(strength, 0.7, vol_confirm, 0.6, symbol)
                qualify(
                    setup_type="bb_squeeze",
                    signal="BUY",
                    score=score,
                    recommended_strategy="bollinger_bounce",
                    reason=f"BB squeeze detected (width percentile: {(1 - pct_rank) * 100:.0f}%)",
                    indicators_payload={"bb_width": round(current_width, 4), "width_percentile": round((1 - pct_rank) * 100, 1)},
                    extra_checks=[
                        (tradability_metrics.bb_width_pct >= 0.80, SETUP_RANGE_TOO_SMALL, "Bollinger width is too narrow"),
                        (tradability_metrics.close_std_pct_24h >= 0.20, SETUP_STRUCTURE_TOO_WEAK, "Compression is too flat to support expansion"),
                    ],
                )

        if len(sma_short) >= 2 and len(sma_long) >= 2:
            gap_pct = abs(sma_short[-1] - sma_long[-1]) / sma_long[-1] * 100 if sma_long[-1] != 0 else 999
            if gap_pct < 1.0:
                approaching_golden = sma_short[-1] > sma_short[-2] and sma_short[-1] < sma_long[-1]
                recent_golden_cross = sma_short[-1] > sma_long[-1] and sma_short[-2] <= sma_long[-2]
                if approaching_golden or recent_golden_cross:
                    vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
                    trend_align = 1.0 if regime in (MarketRegime.TRENDING_UP, MarketRegime.RANGING) else 0.4
                    strength = 0.8 if recent_golden_cross else 0.6
                    score = self._setup_score(strength, trend_align, vol_confirm, 0.6, symbol)
                    reason = "SMA golden cross just occurred" if recent_golden_cross else f"SMA approaching golden cross (gap: {gap_pct:.2f}%)"
                    qualify(
                        setup_type="sma_crossover_proximity",
                        signal="BUY",
                        score=score,
                        recommended_strategy="sma_crossover",
                        reason=reason,
                        indicators_payload={"sma_gap_pct": round(gap_pct, 3)},
                        extra_checks=[
                            (abs(tradability_metrics.short_sma_slope_pct_3) >= 0.15, SETUP_SLOPE_TOO_WEAK, "Short SMA slope is too weak"),
                            (tradability_metrics.close_vs_close_5_pct >= 0.40, SETUP_GAP_ONLY, "Cross is proximity-only without enough price movement"),
                            (tradability_metrics.range_pct_20 >= 1.00, SETUP_RANGE_TOO_SMALL, "Range floor not met for crossover setup"),
                            (abs(tradability_metrics.ema_spread_pct) >= 0.10, SETUP_STRUCTURE_TOO_WEAK, "EMA spread is too compressed for a valid cross"),
                        ],
                    )

        if latest_volume_ratio is not None and latest_volume_ratio > 1.5 and latest_close and previous_close:
            price_up = latest_close > previous_close
            strength = min((latest_volume_ratio - 1.5) / 2.5, 1.0)
            trend_align = 1.0 if regime in (MarketRegime.TRENDING_UP,) and price_up else 0.5
            score = self._setup_score(strength, trend_align, 1.0, 0.7, symbol)
            qualify(
                setup_type="volume_breakout",
                signal="BUY" if price_up else "SELL",
                score=score,
                recommended_strategy="macd_momentum",
                reason=f"Volume breakout ({latest_volume_ratio:.1f}x avg) with price {'up' if price_up else 'down'}",
                indicators_payload={"volume_ratio": round(latest_volume_ratio, 2)},
            )

        if len(macd_line) >= 2 and len(macd_signal) >= 2:
            macd_cross_up = macd_line[-1] > macd_signal[-1] and macd_line[-2] <= macd_signal[-2]
            macd_cross_down = macd_line[-1] < macd_signal[-1] and macd_line[-2] >= macd_signal[-2]
            if macd_cross_up or macd_cross_down:
                signal = "BUY" if macd_cross_up else "SELL"
                hist_val = macd_hist[-1] if macd_hist else 0.0
                strength = min(abs(hist_val) / (abs(macd_signal[-1]) + 1e-9), 1.0) * 0.7
                regime_align = 0.8 if regime in (MarketRegime.TRENDING_UP, MarketRegime.RANGING) else 0.5
                vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
                score = self._setup_score(max(strength, 0.4), regime_align, vol_confirm, 0.6, symbol)
                hist_pct = abs(hist_val) / latest_close * 100 if latest_close else 0.0
                direction = "bullish" if macd_cross_up else "bearish"
                qualify(
                    setup_type="macd_crossover",
                    signal=signal,
                    score=score,
                    recommended_strategy="macd_momentum",
                    reason=f"MACD {direction} crossover (hist: {hist_val:.4f})",
                    indicators_payload={
                        "macd": round(macd_line[-1], 4),
                        "macd_signal": round(macd_signal[-1], 4),
                        "macd_hist": round(hist_val, 4),
                    },
                    extra_checks=[
                        (hist_pct >= 0.03, SETUP_NO_ABSOLUTE_EXPANSION, "MACD histogram magnitude is too small"),
                        (abs(tradability_metrics.directional_displacement_pct_10) >= 0.35, SETUP_NO_ABSOLUTE_EXPANSION, "Price displacement is too weak for MACD follow-through"),
                    ],
                )

        if len(macd_hist) >= 4:
            hist_growing = all(macd_hist[-i] > macd_hist[-i - 1] for i in range(1, 4))
            hist_shrinking = all(macd_hist[-i] < macd_hist[-i - 1] for i in range(1, 4))
            if hist_growing and macd_hist[-1] > 0:
                strength = min(abs(macd_hist[-1]) * 100, 1.0) * 0.6
                score = self._setup_score(max(strength, 0.35), 0.7, 0.6, 0.7, symbol)
                qualify(
                    setup_type="macd_momentum_rising",
                    signal="BUY",
                    score=score,
                    recommended_strategy="macd_momentum",
                    reason=f"MACD histogram rising for 3+ bars ({macd_hist[-1]:.4f})",
                    indicators_payload={"macd_hist": round(macd_hist[-1], 4)},
                    extra_checks=[
                        (abs(tradability_metrics.directional_displacement_pct_10) >= 0.35, SETUP_NO_ABSOLUTE_EXPANSION, "Momentum is rising without enough price displacement"),
                    ],
                )
            elif hist_shrinking and macd_hist[-1] < 0:
                strength = min(abs(macd_hist[-1]) * 100, 1.0) * 0.6
                score = self._setup_score(max(strength, 0.35), 0.7, 0.6, 0.7, symbol)
                qualify(
                    setup_type="macd_momentum_falling",
                    signal="SELL",
                    score=score,
                    recommended_strategy="macd_momentum",
                    reason=f"MACD histogram falling for 3+ bars ({macd_hist[-1]:.4f})",
                    indicators_payload={"macd_hist": round(macd_hist[-1], 4)},
                    extra_checks=[
                        (abs(tradability_metrics.directional_displacement_pct_10) >= 0.35, SETUP_NO_ABSOLUTE_EXPANSION, "Momentum is falling without enough price displacement"),
                    ],
                )

        if latest_close and len(ema_12) >= 2 and len(ema_26) >= 2:
            bullish_stack = latest_close > ema_12[-1] > ema_26[-1]
            bearish_stack = latest_close < ema_12[-1] < ema_26[-1]
            if bullish_stack:
                ema_spread = (ema_12[-1] - ema_26[-1]) / ema_26[-1] * 100
                strength = min(ema_spread / 3.0, 1.0)
                prev_spread = (ema_12[-2] - ema_26[-2]) / ema_26[-2] * 100 if ema_26[-2] != 0 else 0
                widening = ema_spread > prev_spread
                trend_align = 0.9 if regime == MarketRegime.TRENDING_UP else 0.5
                vol_confirm = min(latest_volume_ratio / 0.8, 1.0) if latest_volume_ratio else 0.5
                score = self._setup_score(max(strength, 0.3), trend_align, vol_confirm, 0.8, symbol)
                qualify(
                    setup_type="ema_trend_bullish",
                    signal="BUY",
                    score=score,
                    recommended_strategy="sma_crossover",
                    reason=f"Bullish EMA stack (spread: {ema_spread:.2f}%, {'widening' if widening else 'steady'})",
                    indicators_payload={"ema_spread_pct": round(ema_spread, 3), "widening": widening},
                    extra_checks=[
                        (ema_spread >= 0.15, SETUP_STRUCTURE_TOO_WEAK, "EMA spread is too narrow"),
                        (tradability_metrics.short_sma_slope_pct_3 >= 0.15, SETUP_SLOPE_TOO_WEAK, "Trend slope is too weak"),
                    ],
                )
            elif bearish_stack:
                ema_spread = (ema_26[-1] - ema_12[-1]) / ema_26[-1] * 100
                strength = min(ema_spread / 3.0, 1.0)
                trend_align = 0.9 if regime == MarketRegime.TRENDING_DOWN else 0.5
                vol_confirm = min(latest_volume_ratio / 0.8, 1.0) if latest_volume_ratio else 0.5
                score = self._setup_score(max(strength, 0.3), trend_align, vol_confirm, 0.8, symbol)
                qualify(
                    setup_type="ema_trend_bearish",
                    signal="SELL",
                    score=score,
                    recommended_strategy="sma_crossover",
                    reason=f"Bearish EMA stack (spread: {ema_spread:.2f}%)",
                    indicators_payload={"ema_spread_pct": round(ema_spread, 3)},
                    extra_checks=[
                        (ema_spread >= 0.15, SETUP_STRUCTURE_TOO_WEAK, "EMA spread is too narrow"),
                        (abs(tradability_metrics.short_sma_slope_pct_3) >= 0.15, SETUP_SLOPE_TOO_WEAK, "Trend slope is too weak"),
                    ],
                )

        if latest_adx is not None and latest_adx > 25 and len(ema_12) >= 1 and len(ema_26) >= 1:
            trend_up = ema_12[-1] > ema_26[-1]
            signal = "BUY" if trend_up else "SELL"
            strength = min((latest_adx - 25) / 25, 1.0)
            regime_align = 0.9 if regime in (MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN) else 0.5
            vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
            score = self._setup_score(max(strength, 0.35), regime_align, vol_confirm, 0.8, symbol)
            qualify(
                setup_type="adx_strong_trend",
                signal=signal,
                score=score,
                recommended_strategy="macd_momentum" if trend_up else "rsi_mean_reversion",
                reason=f"ADX strong trend at {latest_adx:.1f} ({'bullish' if trend_up else 'bearish'})",
                indicators_payload={"adx": round(latest_adx, 2)},
                extra_checks=[
                    (abs(tradability_metrics.ema_spread_pct) >= 0.20, SETUP_SLOPE_TOO_WEAK, "EMA spread is too small for a trend setup"),
                    (abs(tradability_metrics.directional_displacement_pct_10) >= 0.50, SETUP_NO_ABSOLUTE_EXPANSION, "Directional displacement is too small for ADX trend"),
                    (tradability_metrics.range_pct_20 >= 1.00, SETUP_RANGE_TOO_SMALL, "Trend setup needs at least 1.00% range"),
                ],
            )

        if bb_upper and bb_lower and latest_close and bb_middle:
            bb_width = bb_upper[-1] - bb_lower[-1]
            if bb_width > 0:
                pct_b = (latest_close - bb_lower[-1]) / bb_width
                if pct_b <= 0.05:
                    strength = max(0, (0.1 - pct_b) / 0.1) * 0.8
                    regime_align = 1.0 if regime == MarketRegime.RANGING else 0.6
                    vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
                    score = self._setup_score(max(strength, 0.4), regime_align, vol_confirm, 0.5, symbol)
                    qualify(
                        setup_type="bb_lower_touch",
                        signal="BUY",
                        score=score,
                        recommended_strategy="bollinger_bounce",
                        reason=f"Price touching lower BB (%B: {pct_b:.2f})",
                        indicators_payload={"pct_b": round(pct_b, 3), "bb_width": round(bb_width, 4)},
                        require_volume=False,
                        extra_checks=[(tradability_metrics.bb_width_pct >= 0.80, SETUP_RANGE_TOO_SMALL, "Bollinger width is too narrow")],
                    )
                elif pct_b >= 0.95:
                    strength = max(0, (pct_b - 0.9) / 0.1) * 0.8
                    regime_align = 1.0 if regime == MarketRegime.RANGING else 0.6
                    vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
                    score = self._setup_score(max(strength, 0.4), regime_align, vol_confirm, 0.5, symbol)
                    qualify(
                        setup_type="bb_upper_touch",
                        signal="SELL",
                        score=score,
                        recommended_strategy="bollinger_bounce",
                        reason=f"Price touching upper BB (%B: {pct_b:.2f})",
                        indicators_payload={"pct_b": round(pct_b, 3), "bb_width": round(bb_width, 4)},
                        require_volume=False,
                        extra_checks=[(tradability_metrics.bb_width_pct >= 0.80, SETUP_RANGE_TOO_SMALL, "Bollinger width is too narrow")],
                    )

        rsi_div = indicators.get("rsi_divergence")
        if rsi_div and getattr(rsi_div, "detected", False) and getattr(rsi_div, "divergence_type", "none") in ("bullish", "bearish"):
            div_type = rsi_div.divergence_type
            signal = "BUY" if div_type == "bullish" else "SELL"
            strength = min(getattr(rsi_div, "strength", 0.5), 1.0)
            regime_align = 0.8 if regime == MarketRegime.RANGING else 0.6
            vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
            score = self._setup_score(max(strength, 0.45), regime_align, vol_confirm, 0.6, symbol)
            qualify(
                setup_type=f"rsi_divergence_{div_type}",
                signal=signal,
                score=score,
                recommended_strategy="rsi_mean_reversion",
                reason=f"RSI {div_type} divergence detected",
                indicators_payload={"rsi": round(latest_rsi or 0, 2), "divergence_type": div_type},
                require_volume=False,
            )

        if latest_close and previous_close and closes and len(closes) >= 20:
            recent = closes[-20:]
            highest_20 = max(recent[:-1])
            lowest_20 = min(recent[:-1])
            if latest_close > highest_20 and latest_close > previous_close:
                breakout_pct = (latest_close - highest_20) / highest_20 * 100
                strength = min(breakout_pct / 2.0, 1.0)
                vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
                trend_align = 0.9 if regime in (MarketRegime.TRENDING_UP, MarketRegime.RANGING) else 0.4
                score = self._setup_score(max(strength, 0.35), trend_align, vol_confirm, 0.8, symbol)
                qualify(
                    setup_type="momentum_breakout_high",
                    signal="BUY",
                    score=score,
                    recommended_strategy="macd_momentum",
                    reason=f"Breaking 20-candle high (+{breakout_pct:.2f}%)",
                    indicators_payload={"breakout_pct": round(breakout_pct, 3), "volume_ratio": round(latest_volume_ratio or 0, 2)},
                )
            elif latest_close < lowest_20 and latest_close < previous_close:
                breakdown_pct = (lowest_20 - latest_close) / lowest_20 * 100
                strength = min(breakdown_pct / 2.0, 1.0)
                vol_confirm = min(latest_volume_ratio / 1.0, 1.0) if latest_volume_ratio else 0.5
                trend_align = 0.9 if regime == MarketRegime.TRENDING_DOWN else 0.4
                score = self._setup_score(max(strength, 0.35), trend_align, vol_confirm, 0.8, symbol)
                qualify(
                    setup_type="momentum_breakout_low",
                    signal="SELL",
                    score=score,
                    recommended_strategy="rsi_mean_reversion",
                    reason=f"Breaking 20-candle low (-{breakdown_pct:.2f}%)",
                    indicators_payload={"breakdown_pct": round(breakdown_pct, 3)},
                )

        for setup in setups:
            setup.indicators = self._to_native(setup.indicators)
            setup.movement_quality = self._to_native(setup.movement_quality)

        return setups, audits

    @staticmethod
    def _to_native(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: OpportunityScanner._to_native(item) for key, item in value.items()}
        if isinstance(value, list):
            return [OpportunityScanner._to_native(item) for item in value]
        if isinstance(value, tuple):
            return tuple(OpportunityScanner._to_native(item) for item in value)

        scalar_to_python = getattr(value, "item", None)
        if callable(scalar_to_python):
            try:
                return scalar_to_python()
            except (TypeError, ValueError):
                return value
        return value

    def _setup_score(
        self,
        signal_strength: float,
        regime_alignment: float,
        volume_confirmation: float,
        trend_alignment: float,
        symbol: str | None = None,
    ) -> float:
        rs_score = 0.5
        if symbol is not None:
            rs = get_relative_strength(symbol)
            if rs is not None:
                rs_score = max(0.0, min(1.0, 0.5 + rs / 10.0))
        return (
            signal_strength * 0.25
            + regime_alignment * 0.20
            + volume_confirmation * 0.20
            + trend_alignment * 0.15
            + rs_score * 0.20
        )

    @staticmethod
    def _estimate_liquidity_usdt(candles: list[Any], window: int = 20) -> float:
        recent = candles[-window:]
        if not recent:
            return 0.0
        quote_volumes = [float(candle.close) * float(candle.volume) for candle in recent]
        return sum(quote_volumes)

    @staticmethod
    def _estimate_one_hour_volume_usdt(candles: list[Any], interval: str) -> float:
        if not candles:
            return 0.0

        normalized = (interval or "").strip().lower()
        if normalized.endswith("m"):
            try:
                minutes = max(int(normalized[:-1]), 1)
            except ValueError:
                minutes = 60
            candles_per_hour = max(1, 60 // minutes)
            recent = candles[-candles_per_hour:]
            return sum(float(candle.close) * float(candle.volume) for candle in recent)

        if normalized.endswith("h"):
            try:
                hours = max(int(normalized[:-1]), 1)
            except ValueError:
                hours = 1
            latest = candles[-1]
            return (float(latest.close) * float(latest.volume)) / hours

        latest = candles[-1]
        return float(latest.close) * float(latest.volume)
