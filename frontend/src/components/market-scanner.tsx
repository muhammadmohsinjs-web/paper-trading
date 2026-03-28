"use client";

import { useState, useCallback } from "react";
import { runManualScan } from "@/lib/api";
import { formatCurrency, formatNumber } from "@/lib/format";
import type { ManualScanResponse, RankedSymbol } from "@/lib/types";
import { MetricStrip, buttonClassName } from "@/components/ui";

const SETUP_LABELS: Record<string, { label: string; color: string }> = {
  rsi_oversold: { label: "RSI Oversold", color: "text-emerald-700" },
  rsi_overbought: { label: "RSI Overbought", color: "text-red-700" },
  bb_squeeze: { label: "BB Squeeze", color: "text-teal-700" },
  bb_lower_touch: { label: "BB Lower Touch", color: "text-emerald-700" },
  bb_upper_touch: { label: "BB Upper Touch", color: "text-red-700" },
  sma_crossover_proximity: { label: "SMA Crossover", color: "text-blue-700" },
  volume_breakout: { label: "Volume Breakout", color: "text-amber-700" },
  macd_crossover: { label: "MACD Crossover", color: "text-amber-700" },
  macd_momentum_rising: { label: "MACD Rising", color: "text-emerald-700" },
  macd_momentum_falling: { label: "MACD Falling", color: "text-red-700" },
  ema_trend_bullish: { label: "EMA Bullish", color: "text-emerald-700" },
  ema_trend_bearish: { label: "EMA Bearish", color: "text-red-700" },
  adx_strong_trend: { label: "ADX Trend", color: "text-violet-700" },
  rsi_divergence_bullish: { label: "RSI Div Bull", color: "text-emerald-700" },
  rsi_divergence_bearish: { label: "RSI Div Bear", color: "text-red-700" },
  momentum_breakout_high: { label: "Breakout High", color: "text-emerald-700" },
  momentum_breakout_low: { label: "Breakdown Low", color: "text-red-700" }
};

function getSetupMeta(setupType: string) {
  return SETUP_LABELS[setupType] ?? { label: setupType, color: "text-slate-600" };
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.min(score * 100, 100);
  const color =
    pct >= 60 ? "bg-emerald-600" : pct >= 40 ? "bg-blue-700" : "bg-slate-300";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-200">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs tabular-nums text-slate-500">{(score * 100).toFixed(0)}</span>
    </div>
  );
}

function SymbolRow({ item, rank }: { item: RankedSymbol; rank: number }) {
  const meta = getSetupMeta(item.setup_type);
  return (
    <div className="grid grid-cols-[2rem_5.5rem_1fr_6rem_7rem_5rem] items-center gap-3 border-b border-slate-200 px-4 py-3 text-sm last:border-b-0">
      <span className="text-xs tabular-nums text-slate-500">#{rank}</span>
      <span className="font-medium text-slate-900">{item.symbol.replace("USDT", "")}</span>
      <div className="min-w-0">
        <span className={`text-xs font-medium uppercase tracking-wider ${meta.color}`}>
          {meta.label}
        </span>
        <p className="mt-0.5 truncate text-xs text-slate-500">{item.reason}</p>
      </div>
      <div className="text-right">
        <span
          className={`text-xs font-medium uppercase ${
            item.regime === "trending_up"
              ? "text-emerald-700"
              : item.regime === "trending_down"
                ? "text-red-700"
                : "text-slate-500"
          }`}
        >
          {item.regime.replace("_", " ")}
        </span>
      </div>
      <div className="text-right text-xs text-slate-500">
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
    <section className="min-w-0 space-y-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-2">
          <h2 className="text-lg font-semibold text-slate-900">Market scanner</h2>
          <p className="text-sm leading-6 text-slate-600">
            Ranked setups from the live universe with table-first output.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <select
            value={interval}
            onChange={(event) => setInterval(event.target.value)}
            className="rounded-[10px] border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-300"
          >
            <option value="5m">5m</option>
            <option value="1h">1h</option>
            <option value="4h">4h</option>
          </select>
          <button onClick={handleScan} disabled={scanning} className={buttonClassName("primary", "md")}>
            {scanning ? "Scanning..." : "Run scan"}
          </button>
        </div>
      </div>

      {error ? <p className="text-sm text-red-700">{error}</p> : null}

      {scanResult ? (
        <>
          <MetricStrip
            items={[
              { label: "Universe", value: formatNumber(scanResult.universe_size, 0) },
              { label: "With data", value: formatNumber(scanResult.symbols_scanned, 0) },
              {
                label: "Setups found",
                value: formatNumber(scanResult.ranked_symbols.length, 0),
                tone: "success"
              },
              {
                label: "Regime",
                value: scanResult.regime.replace("_", " "),
                tone:
                  scanResult.regime === "trending_up"
                    ? "success"
                    : scanResult.regime === "trending_down"
                      ? "danger"
                      : "default"
              }
            ]}
          />

          {scanResult.ranked_symbols.length > 0 ? (
            <div className="table-shell">
              <div className="grid grid-cols-[2rem_5.5rem_1fr_6rem_7rem_5rem] gap-3 border-b border-slate-200 bg-slate-50 px-4 py-2 text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">
                <span>#</span>
                <span>Symbol</span>
                <span>Setup</span>
                <span className="text-right">Regime</span>
                <span className="text-right">Liquidity</span>
                <span className="text-right">Score</span>
              </div>
              {scanResult.ranked_symbols.map((item, idx) => (
                <SymbolRow key={`${item.symbol}-${idx}`} item={item} rank={idx + 1} />
              ))}
            </div>
          ) : (
            <div className="border-t border-slate-200 py-6 text-sm text-slate-500">
              No setups detected across the universe. Market may be in a low-volatility phase.
            </div>
          )}

          <p className="text-xs text-slate-500">
            Scanned at {new Date(scanResult.scanned_at).toLocaleTimeString()} on {interval} timeframe.
          </p>
        </>
      ) : (
        <div className="border-t border-slate-200 py-6">
          <p className="text-sm text-slate-500">
            Press <span className="font-medium text-blue-700">Run scan</span> to evaluate the live universe.
          </p>
          <p className="mt-2 text-xs text-slate-500">
            Detects RSI extremes, MACD crossovers, EMA trends, BB squeezes, ADX trends, and momentum breakouts.
          </p>
        </div>
      )}
    </section>
  );
}
