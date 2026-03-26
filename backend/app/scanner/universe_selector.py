"""Dynamic universe selector — replaces the static coin list with market-driven selection.

Three-stage funnel:
  Stage 1: Universe Discovery — fetch all USDT pairs, apply hard filters
  Stage 2: Activity Ranking — score each candidate on 5 market quality dimensions
  Stage 3: (delegated to OpportunityScanner) — setup detection on the active universe

The selector maintains a cached active universe that refreshes hourly.
"""

from __future__ import annotations

import logging
import math
import time
import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import DEFAULT_SCAN_UNIVERSE, get_settings
from app.engine.tradability import evaluate_symbol_tradability
from app.market.binance_rest import fetch_candles
from app.market.data_store import DataStore
from app.scanner.relative_strength import get_relative_strength
from app.scanner.types import ActivityScore, CandidateInfo, UniverseSnapshot

logger = logging.getLogger(__name__)
settings = get_settings()


class UniverseSelector:
    """Dynamically selects the best coins to scan based on real-time market data.

    Singleton — use ``UniverseSelector.get_instance()``.
    """

    _instance: UniverseSelector | None = None

    def __init__(self) -> None:
        # Stage 1 cache
        self._candidate_pool: list[CandidateInfo] = []
        self._candidate_pool_updated_at: float = 0.0

        # Stage 2 cache
        self._active_universe: list[ActivityScore] = []
        self._active_symbols: list[str] = []
        self._active_universe_updated_at: float = 0.0
        self._previous_active_symbols: set[str] = set()

        # Position-aware retention: symbols that must stay in the universe
        self._retained_symbols: set[str] = set()

        # Last snapshot for API observability
        self._last_snapshot: UniverseSnapshot | None = None
        self._hydrated_symbols_at: dict[str, float] = {}
        self._hydration_semaphore = asyncio.Semaphore(4)

    @classmethod
    def get_instance(cls) -> UniverseSelector:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        cls._instance = None

    # ── Public API ──────────────────────────────────────────────

    async def get_active_universe(
        self,
        *,
        retained_symbols: set[str] | None = None,
        force_refresh: bool = False,
    ) -> list[str]:
        """Return the current active scan universe (list of symbol strings).

        This is the main entry point. It will refresh caches as needed.
        """
        if not settings.dynamic_universe_enabled:
            return list(settings.default_scan_universe)

        if retained_symbols is not None:
            self._retained_symbols = retained_symbols

        now = time.monotonic()

        # Stage 1: refresh candidate pool if stale
        pool_age_hours = (now - self._candidate_pool_updated_at) / 3600
        if force_refresh or not self._candidate_pool or pool_age_hours >= settings.candidate_pool_refresh_hours:
            await self._refresh_candidate_pool()

        # Stage 2: refresh activity ranking if stale
        rank_age_hours = (now - self._active_universe_updated_at) / 3600
        if force_refresh or not self._active_universe or rank_age_hours >= settings.dynamic_universe_refresh_hours:
            await self._refresh_active_universe()

        if not self._active_symbols:
            logger.warning(
                "universe_selector: active universe unavailable, falling back to static universe"
            )
            return list(settings.default_scan_universe)

        return list(self._active_symbols)

    def get_last_snapshot(self) -> UniverseSnapshot | None:
        """Return the last computed universe snapshot for API/debugging."""
        return self._last_snapshot

    def set_retained_symbols(self, symbols: set[str]) -> None:
        """Update the set of symbols that must remain in the universe (open positions)."""
        self._retained_symbols = symbols

    # ── Stage 1: Universe Discovery ─────────────────────────────

    async def _refresh_candidate_pool(self) -> None:
        """Fetch all USDT pairs from Binance and apply hard filters."""
        try:
            tickers = await self._fetch_all_tickers()
            exchange_info = await self._fetch_exchange_info()
        except Exception:
            logger.exception("universe_selector: failed to fetch Binance data, keeping previous pool")
            if not self._candidate_pool:
                # Fallback to static universe if we have nothing
                self._candidate_pool = [
                    CandidateInfo(symbol=s, price=0.0, volume_24h_usdt=0.0, price_change_pct_24h=0.0)
                    for s in DEFAULT_SCAN_UNIVERSE
                ]
            return

        # Build lookup of valid USDT trading pairs
        valid_symbols: set[str] = set()
        symbol_listing_time: dict[str, int] = {}
        for sym_info in exchange_info.get("symbols", []):
            if (
                sym_info.get("status") == "TRADING"
                and sym_info.get("quoteAsset") == "USDT"
                and sym_info.get("isSpotTradingAllowed", False)
            ):
                s = sym_info["symbol"]
                valid_symbols.add(s)
                # Some exchange info responses don't have listing time; default to 0 (old)
                symbol_listing_time[s] = sym_info.get("onboardDate", 0)

        now_ms = int(time.time() * 1000)
        min_age_ms = settings.universe_min_listing_age_days * 86_400_000

        candidates: list[CandidateInfo] = []
        for ticker in tickers:
            symbol = ticker.get("symbol", "")
            if symbol not in valid_symbols:
                continue

            price = float(ticker.get("lastPrice", 0))
            volume_24h = float(ticker.get("quoteVolume", 0))
            price_change_pct = float(ticker.get("priceChangePercent", 0))

            # Hard filters
            if price < settings.universe_min_price:
                continue
            if volume_24h < settings.universe_min_24h_volume_usdt:
                continue

            # Listing age check
            listing_time = symbol_listing_time.get(symbol, 0)
            if listing_time > 0 and (now_ms - listing_time) < min_age_ms:
                continue

            candidates.append(CandidateInfo(
                symbol=symbol,
                price=price,
                volume_24h_usdt=volume_24h,
                price_change_pct_24h=price_change_pct,
            ))

        self._candidate_pool = candidates
        self._candidate_pool_updated_at = time.monotonic()
        logger.info(
            "universe_selector: candidate pool refreshed — %d symbols passed hard filters (from %d USDT pairs)",
            len(candidates), len(valid_symbols),
        )

    # ── Stage 2: Activity Ranking ───────────────────────────────

    async def _refresh_active_universe(self) -> None:
        """Score every candidate and select the top N as the active scan universe."""
        if not self._candidate_pool:
            logger.warning("universe_selector: empty candidate pool, falling back to static universe")
            self._active_symbols = list(settings.default_scan_universe)
            return

        # Fetch fresh 24h tickers for scoring (bulk call)
        try:
            tickers = await self._fetch_all_tickers()
            ticker_map = {t["symbol"]: t for t in tickers}
        except Exception:
            logger.exception("universe_selector: failed to fetch tickers for scoring, keeping previous universe")
            return

        store = DataStore.get_instance()
        scores: list[ActivityScore] = []
        candidate_evaluations: list[CandidateInfo] = []

        for candidate in self._candidate_pool:
            ticker = ticker_map.get(candidate.symbol)
            if not ticker:
                continue

            volume_24h = float(ticker.get("quoteVolume", 0))
            price = float(ticker.get("lastPrice", 0))
            price_change_pct = float(ticker.get("priceChangePercent", 0))

            await self._ensure_symbol_candles(candidate.symbol, store)
            candles = store.get_candles(candidate.symbol, "1h", 200)
            closes = [c.close for c in candles]
            highs = [c.high for c in candles]
            lows = [c.low for c in candles]
            volumes = [c.volume for c in candles]

            tradability = evaluate_symbol_tradability(
                symbol=candidate.symbol,
                closes=closes,
                highs=highs,
                lows=lows,
                volumes=volumes,
                volume_24h_usdt=volume_24h,
            )
            candidate_evaluations.append(
                CandidateInfo(
                    symbol=candidate.symbol,
                    price=price,
                    volume_24h_usdt=volume_24h,
                    price_change_pct_24h=price_change_pct,
                    tradability_passed=tradability.passed,
                    reason_codes=tradability.reason_codes,
                    reason_text=tradability.reason_text,
                    metrics=tradability.metrics.to_dict(),
                    market_quality_score=tradability.market_quality_score,
                )
            )
            if not tradability.passed:
                continue

            # A. Volume Surge Score
            volume_surge = self._score_volume_surge(candidate.symbol, volume_24h, store)

            # B. Volatility Quality Score
            volatility_quality = self._score_volatility_quality(candidate.symbol, price, store)

            # C. Trend Clarity Score
            trend_clarity = self._score_trend_clarity(candidate.symbol, store)

            # D. Liquidity Depth Score
            liquidity_depth = self._score_liquidity_depth(volume_24h)

            # E. Relative Strength Score
            relative_strength = self._score_relative_strength(candidate.symbol)

            # Composite
            composite = (
                volume_surge * settings.universe_volume_surge_weight
                + volatility_quality * settings.universe_volatility_quality_weight
                + trend_clarity * settings.universe_trend_clarity_weight
                + liquidity_depth * settings.universe_liquidity_depth_weight
                + relative_strength * settings.universe_relative_strength_weight
            )

            scores.append(ActivityScore(
                symbol=candidate.symbol,
                activity_score=round(composite, 4),
                volume_surge=round(volume_surge, 4),
                volatility_quality=round(volatility_quality, 4),
                trend_clarity=round(trend_clarity, 4),
                liquidity_depth=round(liquidity_depth, 4),
                relative_strength=round(relative_strength, 4),
                volume_24h_usdt=volume_24h,
                tradability_passed=True,
                reason_codes=[],
                reason_text="Symbol passed tradability and activity checks",
                metrics=tradability.metrics.to_dict(),
            ))

        # Sort by score descending
        scores.sort(key=lambda s: s.activity_score, reverse=True)

        # Select top N
        target_size = settings.dynamic_universe_size
        selected = scores[:target_size]

        # Minimum universe size guarantee — relax if needed
        if len(selected) < settings.dynamic_universe_min_size and len(scores) > len(selected):
            selected = scores[:settings.dynamic_universe_min_size]

        selected_symbols = {s.symbol for s in selected}

        # Mark new entrants
        for s in selected:
            if s.symbol not in self._previous_active_symbols:
                s.is_new_entrant = True

        # Position-aware retention: always include symbols with open positions
        retained_added: list[str] = []
        for sym in self._retained_symbols:
            if sym not in selected_symbols:
                # Find this symbol's score if computed, or create a minimal entry
                existing = next((s for s in scores if s.symbol == sym), None)
                if existing:
                    selected.append(existing)
                else:
                    selected.append(ActivityScore(
                        symbol=sym,
                        activity_score=0.0,
                        volume_surge=0.0,
                        volatility_quality=0.0,
                        trend_clarity=0.0,
                        liquidity_depth=0.0,
                        relative_strength=0.0,
                        volume_24h_usdt=0.0,
                        tradability_passed=False,
                        reason_codes=["RETAINED_OPEN_POSITION"],
                        reason_text="Retained because strategy still has an open position",
                        metrics={},
                    ))
                retained_added.append(sym)
                selected_symbols.add(sym)

        # Compute promoted/demoted
        new_symbols = selected_symbols - self._previous_active_symbols
        removed_symbols = self._previous_active_symbols - selected_symbols

        self._active_universe = selected
        self._active_symbols = [s.symbol for s in selected]
        self._previous_active_symbols = selected_symbols
        self._active_universe_updated_at = time.monotonic()

        self._last_snapshot = UniverseSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            candidate_pool_size=len(self._candidate_pool),
            active_universe_size=len(selected),
            active_symbols=self._active_symbols[:],
            promoted=sorted(new_symbols),
            demoted=sorted(removed_symbols),
            scores=selected,
            candidate_evaluations=candidate_evaluations,
        )

        logger.info(
            "universe_selector: active universe refreshed — %d symbols selected "
            "(+%d promoted, -%d demoted, %d retained for positions)",
            len(selected), len(new_symbols), len(removed_symbols), len(retained_added),
        )
        if new_symbols:
            logger.info("universe_selector: promoted: %s", ", ".join(sorted(new_symbols)[:10]))
        if removed_symbols:
            logger.info("universe_selector: demoted: %s", ", ".join(sorted(removed_symbols)[:10]))

    async def _ensure_symbol_candles(self, symbol: str, store: DataStore) -> None:
        candles = store.get_candles(symbol, "1h", 48)
        if len(candles) >= 48:
            return

        last_refresh = self._hydrated_symbols_at.get(symbol, 0.0)
        now = time.monotonic()
        if now - last_refresh < 900:
            return

        async with self._hydration_semaphore:
            candles = store.get_candles(symbol, "1h", 48)
            if len(candles) >= 48:
                self._hydrated_symbols_at[symbol] = now
                return
            try:
                fetched = await fetch_candles(symbol=symbol, interval="1h", limit=200)
            except Exception:
                logger.exception("universe_selector: failed to hydrate candles for symbol=%s", symbol)
                self._hydrated_symbols_at[symbol] = now
                return
            store.set_candles(symbol, "1h", fetched)
            self._hydrated_symbols_at[symbol] = now

    # ── Scoring Functions ───────────────────────────────────────

    @staticmethod
    def _score_volume_surge(symbol: str, volume_24h: float, store: DataStore) -> float:
        """Score how much current volume exceeds the coin's own normal volume.

        Uses DataStore candles to approximate 7-day average volume.
        Falls back to a moderate score if no candle history available.
        """
        candles = store.get_candles(symbol, "1h", 168)  # 7 days of 1h candles
        if len(candles) < 24:
            # Not enough history — use a neutral score
            return 0.4

        # Compute average hourly quote volume over available history
        hourly_volumes = [c.close * c.volume for c in candles]
        avg_hourly_vol = sum(hourly_volumes) / len(hourly_volumes) if hourly_volumes else 1.0

        # Current hourly rate from 24h volume
        current_hourly_vol = volume_24h / 24.0

        if avg_hourly_vol <= 0:
            return 0.4

        ratio = current_hourly_vol / avg_hourly_vol

        # Scoring: 1.5x-5x is ideal, below 0.5x is bad, above 10x is suspicious
        if ratio < 0.5:
            return max(0.0, ratio / 0.5 * 0.2)  # 0.0 → 0.2
        elif ratio < 1.5:
            return 0.2 + (ratio - 0.5) / 1.0 * 0.3  # 0.2 → 0.5
        elif ratio <= 5.0:
            return 0.5 + (ratio - 1.5) / 3.5 * 0.5  # 0.5 → 1.0
        elif ratio <= 10.0:
            return 1.0 - (ratio - 5.0) / 5.0 * 0.2  # 1.0 → 0.8
        else:
            return 0.6  # Suspicious spike — moderate penalty

    @staticmethod
    def _score_volatility_quality(symbol: str, price: float, store: DataStore) -> float:
        """Score whether volatility is in the tradable sweet spot.

        Ideal ATR/price ratio: 0.3% - 2.5%.
        """
        candles = store.get_candles(symbol, "1h", 20)
        if len(candles) < 15 or price <= 0:
            return 0.3  # Neutral if insufficient data

        # Compute ATR(14) manually
        true_ranges: list[float] = []
        for i in range(1, len(candles)):
            high = candles[i].high
            low = candles[i].low
            prev_close = candles[i - 1].close
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)

        if not true_ranges:
            return 0.3

        atr = sum(true_ranges[-14:]) / min(len(true_ranges), 14)
        atr_pct = (atr / price) * 100

        # Bell curve scoring: peak at 1.0-1.5%
        if atr_pct < 0.1:
            return 0.05
        elif atr_pct < 0.3:
            return 0.1 + (atr_pct - 0.1) / 0.2 * 0.3  # 0.1 → 0.4
        elif atr_pct <= 1.0:
            return 0.4 + (atr_pct - 0.3) / 0.7 * 0.5  # 0.4 → 0.9
        elif atr_pct <= 1.5:
            return 0.9 + (atr_pct - 1.0) / 0.5 * 0.1  # 0.9 → 1.0
        elif atr_pct <= 2.5:
            return 1.0 - (atr_pct - 1.5) / 1.0 * 0.3  # 1.0 → 0.7
        elif atr_pct <= 5.0:
            return 0.7 - (atr_pct - 2.5) / 2.5 * 0.5  # 0.7 → 0.2
        else:
            return 0.1  # Extremely volatile — poor quality

    @staticmethod
    def _score_trend_clarity(symbol: str, store: DataStore) -> float:
        """Score trend clarity using ADX-like directional movement analysis.

        ADX > 25 = strong trend = high score.
        """
        candles = store.get_candles(symbol, "1h", 30)
        if len(candles) < 20:
            return 0.3  # Neutral

        # Compute simplified ADX using directional movement
        plus_dm_sum = 0.0
        minus_dm_sum = 0.0
        tr_sum = 0.0
        lookback = min(len(candles) - 1, 14)

        for i in range(len(candles) - lookback, len(candles)):
            high = candles[i].high
            low = candles[i].low
            prev_high = candles[i - 1].high
            prev_low = candles[i - 1].low
            prev_close = candles[i - 1].close

            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_sum += tr

            up_move = high - prev_high
            down_move = prev_low - low
            if up_move > down_move and up_move > 0:
                plus_dm_sum += up_move
            if down_move > up_move and down_move > 0:
                minus_dm_sum += down_move

        if tr_sum <= 0:
            return 0.3

        plus_di = (plus_dm_sum / tr_sum) * 100
        minus_di = (minus_dm_sum / tr_sum) * 100
        di_sum = plus_di + minus_di
        if di_sum <= 0:
            return 0.3

        dx = abs(plus_di - minus_di) / di_sum * 100

        # Also check EMA consistency: is price consistently on one side?
        closes = [c.close for c in candles]
        ema_50_approx = sum(closes[-min(20, len(closes)):]) / min(20, len(closes))
        recent_closes = closes[-5:]
        consistent_side = all(c > ema_50_approx for c in recent_closes) or all(c < ema_50_approx for c in recent_closes)
        consistency_bonus = 0.1 if consistent_side else 0.0

        # Score based on DX (proxy for ADX)
        if dx < 15:
            score = 0.1 + dx / 15 * 0.2  # 0.1 → 0.3
        elif dx < 25:
            score = 0.3 + (dx - 15) / 10 * 0.3  # 0.3 → 0.6
        elif dx < 40:
            score = 0.6 + (dx - 25) / 15 * 0.3  # 0.6 → 0.9
        else:
            score = 0.9 + min((dx - 40) / 20, 0.1)  # 0.9 → 1.0

        return min(1.0, score + consistency_bonus)

    @staticmethod
    def _score_liquidity_depth(volume_24h_usdt: float) -> float:
        """Tiered scoring based on 24h USDT volume."""
        if volume_24h_usdt >= 50_000_000:
            return 1.0
        elif volume_24h_usdt >= 10_000_000:
            return 0.8
        elif volume_24h_usdt >= 2_000_000:
            return 0.6
        elif volume_24h_usdt >= 500_000:
            return 0.3
        else:
            return 0.1

    @staticmethod
    def _score_relative_strength(symbol: str) -> float:
        """Score relative performance vs BTC.

        Outperforming BTC = higher score, underperforming = lower.
        Moving in lockstep = slight penalty (no alpha).
        """
        rs = get_relative_strength(symbol, interval="1h", lookback_candles=24)
        if rs is None:
            return 0.5  # Neutral

        # Map: +5% vs BTC → 1.0, 0% → 0.5, -5% → 0.0
        # But also penalize lockstep (rs very close to 0)
        score = max(0.0, min(1.0, 0.5 + rs / 10.0))

        # Small penalty for coins moving in exact lockstep with BTC (|rs| < 0.5%)
        if abs(rs) < 0.5:
            score *= 0.9

        return score

    # ── Binance API Helpers ─────────────────────────────────────

    @staticmethod
    async def _fetch_all_tickers() -> list[dict[str, Any]]:
        """Fetch 24h ticker stats for all symbols (single bulk call)."""
        url = f"{settings.binance_rest_url}/api/v3/ticker/24hr"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def _fetch_exchange_info() -> dict[str, Any]:
        """Fetch exchange info (all instruments)."""
        url = f"{settings.binance_rest_url}/api/v3/exchangeInfo"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.json()
