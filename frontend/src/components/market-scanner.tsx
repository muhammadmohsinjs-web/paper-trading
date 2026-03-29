"use client";

import { useState, useCallback } from "react";
import { refreshScannerLiveData, runManualScan } from "@/lib/api";
import { cn, formatCurrency, formatNumber } from "@/lib/format";
import type {
  FunnelStats,
  ManualScanResponse,
  RankedSymbol,
  ScannerRefreshResponse,
} from "@/lib/types";
import { MetricStrip, CoinIcon, buttonClassName } from "@/components/ui";

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
      <span className="flex items-center gap-2 font-medium text-slate-900">
        <CoinIcon symbol={item.symbol} />
        {item.symbol.replace("USDT", "")}
      </span>
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

function FiltrationFunnel({ funnel }: { funnel: FunnelStats }) {
  const stages = [
    { label: "USDT pairs discovered", count: funnel.total_usdt_pairs },
    { label: "After hard filters", count: funnel.after_hard_filters },
    { label: "After tradability", count: funnel.after_tradability },
    { label: "Active universe", count: funnel.active_universe, accent: true },
    { label: "With sufficient data", count: funnel.with_data },
    { label: "Setup detected", count: funnel.after_setup_detection },
    { label: "Passed liquidity floor", count: funnel.after_liquidity_floor },
    { label: "Final ranked", count: funnel.final_ranked, success: true },
  ];

  const maxCount = stages[0].count || 1;

  return (
    <div className="table-shell">
      <div className="border-b border-slate-200 bg-slate-50 px-4 py-2 text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">
        Filtration funnel
      </div>
      <div className="divide-y divide-slate-100">
        {stages.map((stage) => {
          const pct = Math.max((stage.count / maxCount) * 100, 2);
          const dropped = stages[0].count - stage.count;
          return (
            <div key={stage.label} className="flex items-center gap-4 px-4 py-2">
              <span className="w-40 shrink-0 text-xs text-slate-600">{stage.label}</span>
              <div className="flex-1">
                <div
                  className={cn(
                    "h-3.5 rounded",
                    stage.success ? "bg-emerald-500" : stage.accent ? "bg-blue-500" : "bg-slate-300"
                  )}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="w-12 text-right text-sm font-medium tabular-nums text-slate-900">
                {formatNumber(stage.count, 0)}
              </span>
              {dropped > 0 && !stage.success && !stage.accent ? (
                <span className="w-16 text-right text-[11px] tabular-nums text-slate-400">
                  -{formatNumber(dropped, 0)}
                </span>
              ) : (
                <span className="w-16" />
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export function MarketScanner() {
  const [scanResult, setScanResult] = useState<ManualScanResponse | null>(null);
  const [scanning, setScanning] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshResult, setRefreshResult] = useState<ScannerRefreshResponse | null>(null);
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

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const refreshed = await refreshScannerLiveData();
      setRefreshResult(refreshed);
      const result = await runManualScan(interval, 15);
      setScanResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed");
    } finally {
      setRefreshing(false);
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
          <button
            onClick={handleRefresh}
            disabled={refreshing || scanning}
            className={buttonClassName("secondary", "md")}
          >
            {refreshing ? "Refreshing..." : "Refresh Binance"}
          </button>
          <button
            onClick={handleScan}
            disabled={scanning || refreshing}
            className={buttonClassName("primary", "md")}
          >
            {scanning ? "Scanning..." : "Run scan"}
          </button>
        </div>
      </div>

      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {refreshResult ? (
        <p className="text-xs text-slate-500">
          Binance refresh loaded {formatNumber(refreshResult.symbols_refreshed, 0)} symbols across{" "}
          {formatNumber(refreshResult.successful_pairs, 0)}/
          {formatNumber(refreshResult.requested_pairs, 0)} symbol-interval pairs.
        </p>
      ) : null}

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

          {scanResult.funnel ? <FiltrationFunnel funnel={scanResult.funnel} /> : null}

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
