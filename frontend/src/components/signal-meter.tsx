"use client";

import { useEffect, useState, useCallback } from "react";
import { getSignal } from "@/lib/api";
import { cn } from "@/lib/format";
import type { SignalData } from "@/lib/types";

const VOTE_LABELS: Record<string, string> = {
  rsi: "RSI",
  macd: "MACD",
  sma: "SMA",
  ema: "EMA",
  volume: "Volume",
  ai: "AI",
};

function VoteBar({ label, value, weight }: { label: string; value: number; weight: number }) {
  const pct = Math.abs(value) * 100;
  const isBullish = value > 0;
  const isBearish = value < 0;

  return (
    <div className="flex items-center gap-3">
      <span className="w-16 shrink-0 text-xs text-mist/55">{label}</span>
      <div className="relative h-2 flex-1 rounded-full bg-white/8 overflow-hidden">
        {isBullish && (
          <div
            className="absolute left-1/2 top-0 h-full rounded-r-full bg-rise/70 transition-all duration-700"
            style={{ width: `${pct / 2}%` }}
          />
        )}
        {isBearish && (
          <div
            className="absolute right-1/2 top-0 h-full rounded-l-full bg-fall/70 transition-all duration-700"
            style={{ width: `${pct / 2}%` }}
          />
        )}
        <div className="absolute left-1/2 top-0 h-full w-px bg-mist/20" />
      </div>
      <span
        className={cn(
          "w-12 text-right text-xs tabular-nums",
          isBullish && "text-rise",
          isBearish && "text-fall",
          !isBullish && !isBearish && "text-mist/40"
        )}
      >
        {value > 0 ? "+" : ""}
        {value.toFixed(2)}
      </span>
      <span className="w-8 text-right text-[10px] text-mist/35">{(weight * 100).toFixed(0)}%</span>
    </div>
  );
}

function ConfidenceGauge({ score, confidence, signal }: { score: number; confidence: number; signal: string }) {
  // Score range: -1 to 1. Map to 0-100 for the gauge.
  const gaugePos = ((score + 1) / 2) * 100;
  const confPct = (confidence * 100).toFixed(1);

  const tierLabel =
    confidence >= 0.8 ? "FULL" : confidence >= 0.6 ? "REDUCED" : confidence >= 0.5 ? "SMALL" : "NONE";
  const tierColor =
    confidence >= 0.8
      ? "text-rise"
      : confidence >= 0.6
        ? "text-gold"
        : confidence >= 0.5
          ? "text-mist/70"
          : "text-mist/40";

  const allocationPct =
    confidence >= 0.8 ? "60%" : confidence >= 0.6 ? "30%" : confidence >= 0.5 ? "~12%" : "0%";

  return (
    <div className="space-y-4">
      {/* Main gauge bar */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-fall/70">SELL</span>
          <span className="text-mist/40">HOLD</span>
          <span className="text-rise/70">BUY</span>
        </div>
        <div className="relative h-3 rounded-full overflow-hidden bg-gradient-to-r from-fall/20 via-white/5 to-rise/20">
          {/* Buy/Sell threshold markers */}
          <div className="absolute left-[25%] top-0 h-full w-px bg-fall/30" />
          <div className="absolute left-[75%] top-0 h-full w-px bg-rise/30" />
          {/* Confidence gate markers */}
          <div className="absolute left-1/2 top-0 h-full w-px bg-mist/25" />
          {/* Score needle */}
          <div
            className="absolute top-0 h-full w-1 rounded-full transition-all duration-700"
            style={{
              left: `calc(${gaugePos}% - 2px)`,
              backgroundColor: score > 0.1 ? "#b8ff67" : score < -0.1 ? "#ff7b5a" : "#f3c96b",
              boxShadow:
                score > 0.1
                  ? "0 0 8px rgba(184,255,103,0.5)"
                  : score < -0.1
                    ? "0 0 8px rgba(255,123,90,0.5)"
                    : "0 0 8px rgba(243,201,107,0.3)",
            }}
          />
        </div>
        <div className="flex items-center justify-between text-[10px] text-mist/30">
          <span>-1.0</span>
          <span>-0.5</span>
          <span>0</span>
          <span>+0.5</span>
          <span>+1.0</span>
        </div>
      </div>

      {/* Signal + Confidence readout */}
      <div className="grid grid-cols-3 gap-3 text-center">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-mist/40">Signal</p>
          <p
            className={cn(
              "mt-1 text-lg font-semibold",
              signal === "BUY" && "text-rise",
              signal === "SELL" && "text-fall",
              signal === "HOLD" && "text-gold"
            )}
          >
            {signal}
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-widest text-mist/40">Confidence</p>
          <p className="mt-1 text-lg font-semibold text-sand">{confPct}%</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-widest text-mist/40">Allocation</p>
          <p className={cn("mt-1 text-lg font-semibold", tierColor)}>
            {allocationPct}
          </p>
          <p className={cn("text-[10px]", tierColor)}>{tierLabel}</p>
        </div>
      </div>
    </div>
  );
}

export function SignalMeter({ symbol = "BTCUSDT", interval = "1h" }: { symbol?: string; interval?: string }) {
  const [signal, setSignal] = useState<SignalData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchSignal = useCallback(async () => {
    try {
      const data = await getSignal(symbol, interval);
      setSignal(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load signal");
    } finally {
      setLoading(false);
    }
  }, [symbol, interval]);

  useEffect(() => {
    fetchSignal();
    const timer = setInterval(fetchSignal, 30_000); // Refresh every 30s
    return () => clearInterval(timer);
  }, [fetchSignal]);

  if (loading) {
    return (
      <div className="panel p-6 space-y-3">
        <p className="text-xs uppercase tracking-[0.3em] text-gold">Signal Meter</p>
        <p className="text-sm text-mist/50">Loading indicators...</p>
      </div>
    );
  }

  if (error || !signal) {
    return (
      <div className="panel p-6 space-y-3">
        <p className="text-xs uppercase tracking-[0.3em] text-gold">Signal Meter</p>
        <p className="text-sm text-fall/70">{error || "Waiting for candle data (need 50+ candles)..."}</p>
      </div>
    );
  }

  const voteEntries = Object.entries(signal.votes).filter(([key]) => key in VOTE_LABELS);

  return (
    <div className="panel p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.3em] text-gold">Signal Meter</p>
          <p className="mt-1 text-sm text-mist/50">
            {signal.symbol} {signal.interval} composite
          </p>
        </div>
        <div className="text-right">
          <p
            className={cn(
              "text-2xl font-semibold tabular-nums",
              signal.composite_score > 0.1 && "text-rise",
              signal.composite_score < -0.1 && "text-fall",
              Math.abs(signal.composite_score) <= 0.1 && "text-gold"
            )}
          >
            {signal.composite_score > 0 ? "+" : ""}
            {signal.composite_score.toFixed(3)}
          </p>
          <p className="text-[10px] text-mist/40">COMPOSITE SCORE</p>
        </div>
      </div>

      <ConfidenceGauge score={signal.composite_score} confidence={signal.confidence} signal={signal.signal} />

      {/* Per-indicator votes */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="text-[10px] uppercase tracking-widest text-mist/40">Indicator Votes</p>
          <p className="text-[10px] text-mist/30">vote / weight</p>
        </div>
        <div className="space-y-1.5">
          {voteEntries.map(([key, value]) => (
            <VoteBar
              key={key}
              label={VOTE_LABELS[key] ?? key}
              value={value}
              weight={signal.weights[key] ?? 0}
            />
          ))}
        </div>
      </div>

      {/* Key indicators */}
      <div className="grid grid-cols-3 gap-3 rounded-2xl bg-white/5 p-3 text-center">
        <div>
          <p className="text-[10px] text-mist/40">RSI</p>
          <p
            className={cn(
              "mt-0.5 text-sm font-medium tabular-nums",
              signal.indicators.rsi !== null && signal.indicators.rsi > 70 && "text-fall",
              signal.indicators.rsi !== null && signal.indicators.rsi < 30 && "text-rise",
              (signal.indicators.rsi === null ||
                (signal.indicators.rsi >= 30 && signal.indicators.rsi <= 70)) &&
                "text-sand"
            )}
          >
            {signal.indicators.rsi?.toFixed(1) ?? "--"}
          </p>
        </div>
        <div>
          <p className="text-[10px] text-mist/40">Vol Ratio</p>
          <p
            className={cn(
              "mt-0.5 text-sm font-medium tabular-nums",
              signal.indicators.volume_ratio !== null && signal.indicators.volume_ratio > 1.2 && "text-rise",
              signal.indicators.volume_ratio !== null && signal.indicators.volume_ratio < 0.7 && "text-fall",
              (signal.indicators.volume_ratio === null ||
                (signal.indicators.volume_ratio >= 0.7 && signal.indicators.volume_ratio <= 1.2)) &&
                "text-sand"
            )}
          >
            {signal.indicators.volume_ratio?.toFixed(2) ?? "--"}x
          </p>
        </div>
        <div>
          <p className="text-[10px] text-mist/40">ATR</p>
          <p className="mt-0.5 text-sm font-medium tabular-nums text-sand">
            ${signal.indicators.atr?.toFixed(0) ?? "--"}
          </p>
        </div>
      </div>

      {signal.dampening_multiplier < 1 && (
        <p className="text-[10px] text-fall/60">
          Low volume dampening active ({(signal.dampening_multiplier * 100).toFixed(0)}%)
        </p>
      )}
    </div>
  );
}
