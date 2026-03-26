"use client";

import { useState, useCallback } from "react";
import { runManualScan } from "@/lib/api";
import { formatCurrency, formatNumber } from "@/lib/format";
import type { ManualScanResponse, RankedSymbol } from "@/lib/types";

const SETUP_LABELS: Record<string, { label: string; color: string }> = {
  rsi_oversold: { label: "RSI Oversold", color: "text-rise" },
  rsi_overbought: { label: "RSI Overbought", color: "text-fall" },
  bb_squeeze: { label: "BB Squeeze", color: "text-teal-400" },
  bb_lower_touch: { label: "BB Lower Touch", color: "text-rise" },
  bb_upper_touch: { label: "BB Upper Touch", color: "text-fall" },
  sma_crossover_proximity: { label: "SMA Crossover", color: "text-blue-400" },
  volume_breakout: { label: "Volume Breakout", color: "text-amber-400" },
  macd_crossover: { label: "MACD Crossover", color: "text-amber-400" },
  macd_momentum_rising: { label: "MACD Rising", color: "text-rise" },
  macd_momentum_falling: { label: "MACD Falling", color: "text-fall" },
  ema_trend_bullish: { label: "EMA Bullish", color: "text-rise" },
  ema_trend_bearish: { label: "EMA Bearish", color: "text-fall" },
  adx_strong_trend: { label: "ADX Trend", color: "text-purple-400" },
  rsi_divergence_bullish: { label: "RSI Div Bull", color: "text-rise" },
  rsi_divergence_bearish: { label: "RSI Div Bear", color: "text-fall" },
  momentum_breakout_high: { label: "Breakout High", color: "text-rise" },
  momentum_breakout_low: { label: "Breakdown Low", color: "text-fall" },
};

function getSetupMeta(setupType: string) {
  return SETUP_LABELS[setupType] ?? { label: setupType, color: "text-mist/70" };
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(score * 100, 100);
  const color =
    pct >= 60 ? "bg-rise" : pct >= 40 ? "bg-gold" : "bg-mist/30";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-white/8">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums text-mist/60">{(score * 100).toFixed(0)}</span>
    </div>
  );
}

function SymbolRow({ item, rank }: { item: RankedSymbol; rank: number }) {
  const meta = getSetupMeta(item.setup_type);
  return (
    <div className="grid grid-cols-[2rem_5.5rem_1fr_6rem_7rem_5rem] items-center gap-3 border-b border-white/5 px-4 py-3 text-sm last:border-b-0">
      <span className="text-xs tabular-nums text-mist/40">#{rank}</span>
      <span className="font-medium text-sand">{item.symbol.replace("USDT", "")}</span>
      <div className="min-w-0">
        <span className={`text-xs font-medium uppercase tracking-wider ${meta.color}`}>
          {meta.label}
        </span>
        <p className="mt-0.5 truncate text-xs text-mist/50">{item.reason}</p>
      </div>
      <div className="text-right">
        <span className={`text-xs font-medium uppercase ${item.regime === "trending_up" ? "text-rise" : item.regime === "trending_down" ? "text-fall" : "text-mist/60"}`}>
          {item.regime.replace("_", " ")}
        </span>
      </div>
      <div className="text-right text-xs text-mist/50">
        {formatCurrency(item.liquidity_usdt, true)}
      </div>
      <div className="flex justify-end">
        <ScoreBar score={item.score} />
      </div>
    </div>
  );
}

export function MarketScanner() {
  const [scanResult, setScanResult] = useState<ManualScanResponse | null>(null);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [interval, setInterval] = useState("1h");

  const handleScan = useCallback(async () => {
    setScanning(true);
    setError(null);
    try {
      const result = await runManualScan(interval, 15);
      setScanResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  }, [interval]);

  return (
    <section className="panel min-w-0 overflow-hidden p-0 rise-in">
      <div className="border-b border-white/6 px-6 py-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-[0.28em] text-gold">Live Scanner</p>
            <h3 className="mt-2 text-2xl font-semibold text-sand">Market Scanner</h3>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-mist/62">
              Scan the full universe for trading setups across 12 signal types.
              Results are ranked by composite score with diversification filtering.
            </p>
          </div>
          <div className="flex flex-shrink-0 items-center gap-3">
            <select
              value={interval}
              onChange={(e) => setInterval(e.target.value)}
              className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-sand outline-none focus:border-gold/40"
            >
              <option value="5m">5m</option>
              <option value="1h">1h</option>
              <option value="4h">4h</option>
            </select>
            <button
              onClick={handleScan}
              disabled={scanning}
              className="rounded-full bg-gold/90 px-5 py-2 text-sm font-medium text-black transition hover:bg-gold disabled:opacity-50"
            >
              {scanning ? (
                <span className="flex items-center gap-2">
                  <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-black/30 border-t-black" />
                  Scanning...
                </span>
              ) : (
                "Scan Now"
              )}
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="border-b border-fall/20 bg-fall/[0.06] px-6 py-3 text-sm text-fall">
          {error}
        </div>
      )}

      {scanResult ? (
        <>
          <div className="grid grid-cols-4 gap-4 border-b border-white/6 px-6 py-4">
            <div>
              <p className="text-[10px] uppercase tracking-[0.22em] text-mist/40">Universe</p>
              <p className="mt-1 text-lg font-semibold text-sand">
                {formatNumber(scanResult.universe_size, 0)}
              </p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-[0.22em] text-mist/40">With Data</p>
              <p className="mt-1 text-lg font-semibold text-sand">
                {formatNumber(scanResult.symbols_scanned, 0)}
              </p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-[0.22em] text-mist/40">Setups Found</p>
              <p className="mt-1 text-lg font-semibold text-rise">
                {formatNumber(scanResult.ranked_symbols.length, 0)}
              </p>
            </div>
            <div>
              <p className="text-[10px] uppercase tracking-[0.22em] text-mist/40">Regime</p>
              <p className={`mt-1 text-lg font-semibold capitalize ${
                scanResult.regime === "trending_up" ? "text-rise" :
                scanResult.regime === "trending_down" ? "text-fall" :
                "text-sand"
              }`}>
                {scanResult.regime.replace("_", " ")}
              </p>
            </div>
          </div>

          {scanResult.ranked_symbols.length > 0 ? (
            <div>
              <div className="grid grid-cols-[2rem_5.5rem_1fr_6rem_7rem_5rem] gap-3 border-b border-white/8 px-4 py-2 text-[10px] uppercase tracking-[0.2em] text-mist/35">
                <span>#</span>
                <span>Symbol</span>
                <span>Setup</span>
                <span className="text-right">Regime</span>
                <span className="text-right">Liquidity</span>
                <span className="text-right">Score</span>
              </div>
              {scanResult.ranked_symbols.map((item, idx) => (
                <SymbolRow key={item.symbol} item={item} rank={idx + 1} />
              ))}
            </div>
          ) : (
            <div className="px-6 py-8 text-center text-sm text-mist/50">
              No setups detected across the universe. Market may be in a low-volatility phase.
            </div>
          )}

          <div className="border-t border-white/6 px-6 py-3 text-xs text-mist/40">
            Scanned at {new Date(scanResult.scanned_at).toLocaleTimeString()} on {interval} timeframe
          </div>
        </>
      ) : (
        <div className="px-6 py-12 text-center">
          <p className="text-sm text-mist/50">
            Press <span className="font-medium text-gold">Scan Now</span> to run a fresh market scan
            across all {35} symbols in the universe.
          </p>
          <p className="mt-2 text-xs text-mist/35">
            Detects RSI extremes, MACD crossovers, EMA trends, BB squeezes, ADX trends, momentum breakouts, and more.
          </p>
        </div>
      )}
    </section>
  );
}
