"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { PriceChart } from "@/components/price-chart";
import {
  buildStrategyIndicatorDisplay,
  StrategyIndicatorPanels
} from "@/components/strategy-indicators";
import { OpenPositions } from "@/components/open-positions";
import { TradeLog } from "@/components/trade-log";
import { WalletSummary } from "@/components/wallet-summary";
import { AICallLog } from "@/components/ai-call-log";
import { useLiveFeed } from "@/hooks/use-live-feed";
import { executeStrategy, aiPreview, type AIPreviewResponse } from "@/lib/api";
import { MetricStrip, PageHeader, Surface, CoinIcon, buttonClassName } from "@/components/ui";
import { STRATEGY_TYPE_META } from "@/lib/types";
import type {
  Candle,
  EquityPoint,
  IndicatorSeriesPoint,
  MarketIndicatorsResponse,
  Position,
  StrategyWithStats,
  Trade,
  TradeSummary,
  StrategyType
} from "@/lib/types";

type ExecutionGuide = {
  statusLabel: string;
  tone: "neutral" | "accent" | "success" | "warning";
  summary: string;
  buyRule: string;
  sellRule: string;
  details: Array<{ label: string; value: string }>;
  note?: string;
};

function latestPointValue(series: IndicatorSeriesPoint[] | undefined, offset = 0) {
  if (!series?.length || series.length <= offset) {
    return null;
  }
  const point = series[series.length - 1 - offset];
  return typeof point?.value === "number" ? point.value : null;
}

function formatNumber(value: number | null, digits = 2) {
  if (value == null || Number.isNaN(value)) {
    return "--";
  }
  return value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  });
}

function formatSignedNumber(value: number | null, digits = 2) {
  if (value == null || Number.isNaN(value)) {
    return "--";
  }
  const formatted = formatNumber(Math.abs(value), digits);
  return `${value > 0 ? "+" : value < 0 ? "-" : ""}${formatted}`;
}

function formatDistance(current: number | null, target: number | null, digits = 2) {
  if (current == null || target == null || Number.isNaN(current) || Number.isNaN(target)) {
    return "--";
  }
  const delta = current - target;
  const pct = target !== 0 ? (delta / target) * 100 : null;
  return `${formatSignedNumber(delta, digits)}${pct != null ? ` (${formatSignedNumber(pct, 2)}%)` : ""}`;
}

function buildExecutionGuide({
  strategyType,
  indicators,
  currentPrice,
  previousClose,
  hasPosition,
  config
}: {
  strategyType: StrategyType;
  indicators: MarketIndicatorsResponse;
  currentPrice: number | null;
  previousClose: number | null;
  hasPosition: boolean;
  config: Record<string, unknown> | null | undefined;
}): ExecutionGuide {
  const { series } = indicators;
  const currentRsi = latestPointValue(series.rsi);
  const previousRsi = latestPointValue(series.rsi, 1);
  const currentMacd = latestPointValue(series.macd_line);
  const previousMacd = latestPointValue(series.macd_line, 1);
  const currentSignal = latestPointValue(series.macd_signal);
  const previousSignal = latestPointValue(series.macd_signal, 1);
  const currentHistogram = latestPointValue(series.macd_histogram);
  const previousHistogram = latestPointValue(series.macd_histogram, 1);
  const currentSmaShort = latestPointValue(series.sma_short);
  const previousSmaShort = latestPointValue(series.sma_short, 1);
  const currentSmaLong = latestPointValue(series.sma_long);
  const previousSmaLong = latestPointValue(series.sma_long, 1);
  const currentEmaFast = latestPointValue(series.ema_12);
  const previousEmaFast = latestPointValue(series.ema_12, 1);
  const currentEmaSlow = latestPointValue(series.ema_26);
  const previousEmaSlow = latestPointValue(series.ema_26, 1);
  const currentVolumeRatio = latestPointValue(series.volume_ratio);
  const currentBbUpper = latestPointValue(series.bollinger_upper);
  const currentBbMiddle = latestPointValue(series.bollinger_middle);
  const currentBbLower = latestPointValue(series.bollinger_lower);

  if (strategyType === "sma_crossover") {
    const buyCross =
      !hasPosition &&
      previousSmaShort != null &&
      previousSmaLong != null &&
      currentSmaShort != null &&
      currentSmaLong != null &&
      previousSmaShort <= previousSmaLong &&
      currentSmaShort > currentSmaLong;
    const sellCross =
      hasPosition &&
      previousSmaShort != null &&
      previousSmaLong != null &&
      currentSmaShort != null &&
      currentSmaLong != null &&
      previousSmaShort >= previousSmaLong &&
      currentSmaShort < currentSmaLong;
    const volumeConfirmed = currentVolumeRatio == null || currentVolumeRatio >= 0.8;
    const shortPeriod =
      typeof config?.sma_short === "number" ? config.sma_short : indicators.config.sma_short;
    const longPeriod =
      typeof config?.sma_long === "number" ? config.sma_long : indicators.config.sma_long;
    const gap = currentSmaShort != null && currentSmaLong != null ? currentSmaShort - currentSmaLong : null;

    return {
      statusLabel: sellCross ? "SELL ready" : buyCross && volumeConfirmed ? "BUY ready" : "Waiting for crossover",
      tone: sellCross || (buyCross && volumeConfirmed) ? "success" : buyCross ? "warning" : "neutral",
      summary:
        buyCross && !volumeConfirmed
          ? `The fast SMA already crossed above the slow SMA, but execution is still blocked because volume ratio is ${formatNumber(currentVolumeRatio, 2)} and this strategy rejects low-volume entries below 0.80.`
          : sellCross
            ? "The fast SMA crossed back below the slow SMA, so an open position in this coin is eligible for a sell on the current candle."
            : buyCross
              ? "The fast SMA crossed above the slow SMA on the current candle and volume confirmation is in place, so this coin is eligible for a buy."
              : `This coin will trade only on a fresh SMA crossover. The current fast-vs-slow gap is ${formatSignedNumber(gap, 2)}.`,
      buyRule: `BUY executes when SMA ${shortPeriod} crosses above SMA ${longPeriod} on the current candle and volume ratio is at least 0.80.`,
      sellRule: `SELL executes when SMA ${shortPeriod} crosses back below SMA ${longPeriod} while this coin has an open position.`,
      details: [
        { label: `SMA ${shortPeriod}`, value: formatNumber(currentSmaShort, 2) },
        { label: `SMA ${longPeriod}`, value: formatNumber(currentSmaLong, 2) },
        { label: "Gap", value: formatSignedNumber(gap, 2) },
        { label: "Volume ratio", value: formatNumber(currentVolumeRatio, 2) }
      ]
    };
  }

  if (strategyType === "rsi_mean_reversion") {
    const sellReady = hasPosition && currentRsi != null && currentRsi > 70;
    const deepOversoldBuy = !hasPosition && currentRsi != null && currentRsi < 20;
    const oversoldBuy = !hasPosition && currentRsi != null && currentRsi < 25;

    return {
      statusLabel: sellReady ? "SELL ready" : deepOversoldBuy ? "BUY ready" : oversoldBuy ? "Light BUY ready" : "Waiting for RSI extreme",
      tone: sellReady || deepOversoldBuy ? "success" : oversoldBuy ? "accent" : "neutral",
      summary: sellReady
        ? `RSI is ${formatNumber(currentRsi, 1)}, which is above the 70 overbought exit threshold, so this coin is eligible for a sell if a position is open.`
        : deepOversoldBuy
          ? `RSI is ${formatNumber(currentRsi, 1)}, which is below 20, so this coin is eligible for the deeper oversold buy path.`
          : oversoldBuy
            ? `RSI is ${formatNumber(currentRsi, 1)}, which is below 25, so this coin is eligible for the smaller oversold buy path.`
            : `This strategy waits for RSI extremes. Current RSI is ${formatNumber(currentRsi, 1)} and no direct threshold trigger is active from the visible data.`,
      buyRule: "BUY executes below RSI 20 for a deeper oversold entry, or below RSI 25 for a smaller oversold entry. The engine can also buy on bullish RSI divergence below RSI 35.",
      sellRule: "SELL executes when RSI moves above 70 while this coin has an open position.",
      details: [
        { label: "Current RSI", value: formatNumber(currentRsi, 1) },
        { label: "Previous RSI", value: formatNumber(previousRsi, 1) },
        { label: "Distance to 25", value: formatDistance(currentRsi, 25, 1) },
        { label: "Distance to 70", value: formatDistance(currentRsi, 70, 1) }
      ],
      note: "Bullish divergence is part of the live strategy, but that divergence signal is not exposed in the current page payload."
    };
  }

  if (strategyType === "macd_momentum") {
    const buyCross =
      !hasPosition &&
      previousMacd != null &&
      previousSignal != null &&
      currentMacd != null &&
      currentSignal != null &&
      previousMacd <= previousSignal &&
      currentMacd > currentSignal;
    const sellCross =
      hasPosition &&
      previousMacd != null &&
      previousSignal != null &&
      currentMacd != null &&
      currentSignal != null &&
      previousMacd >= previousSignal &&
      currentMacd < currentSignal;
    const strongBuy =
      buyCross &&
      currentHistogram != null &&
      previousHistogram != null &&
      currentHistogram > previousHistogram &&
      currentHistogram > 0;
    const gap = currentMacd != null && currentSignal != null ? currentMacd - currentSignal : null;

    return {
      statusLabel: sellCross ? "SELL ready" : buyCross ? "BUY ready" : "Waiting for MACD cross",
      tone: sellCross || buyCross ? "success" : "neutral",
      summary: sellCross
        ? "MACD crossed below the signal line on the current candle, so an open position in this coin is eligible for a sell."
        : strongBuy
          ? "MACD crossed above the signal line with a rising positive histogram, so the stronger momentum-buy path is active."
          : buyCross
            ? "MACD crossed above the signal line, so the standard momentum-buy path is active."
            : `This strategy waits for a fresh MACD crossover. The current MACD minus signal spread is ${formatSignedNumber(gap, 3)}.`,
      buyRule: "BUY executes when MACD crosses above the signal line. Position size is 50% if histogram is rising and already positive; otherwise 30%.",
      sellRule: "SELL executes when MACD crosses below the signal line while this coin has an open position.",
      details: [
        { label: "MACD", value: formatNumber(currentMacd, 3) },
        { label: "Signal", value: formatNumber(currentSignal, 3) },
        { label: "Gap", value: formatSignedNumber(gap, 3) },
        { label: "Histogram", value: formatSignedNumber(currentHistogram, 3) }
      ]
    };
  }

  if (strategyType === "bollinger_bounce") {
    const bandWidth =
      currentBbUpper != null && currentBbLower != null ? currentBbUpper - currentBbLower : null;
    const proximity =
      currentPrice != null &&
      currentBbLower != null &&
      bandWidth != null &&
      bandWidth > 0
        ? (currentPrice - currentBbLower) / bandWidth
        : null;
    const buyReady = !hasPosition && currentPrice != null && currentBbLower != null && currentPrice <= currentBbLower;
    const proximityBuy = !buyReady && !hasPosition && proximity != null && proximity <= 0.2;
    const upperSell = hasPosition && currentPrice != null && currentBbUpper != null && currentPrice >= currentBbUpper;
    const middleSell =
      hasPosition &&
      currentPrice != null &&
      currentBbMiddle != null &&
      previousClose != null &&
      currentPrice < currentBbMiddle &&
      previousClose >= currentBbMiddle;

    return {
      statusLabel: upperSell || middleSell ? "SELL ready" : buyReady ? "BUY ready" : proximityBuy ? "Watch lower band" : "Waiting for band touch",
      tone: upperSell || middleSell || buyReady ? "success" : proximityBuy ? "accent" : "neutral",
      summary: upperSell
        ? "Price is at or above the upper Bollinger Band, so an open position in this coin is eligible for a sell."
        : middleSell
          ? "Price lost the middle Bollinger Band after the prior close held it, so the protective middle-band sell condition is active."
          : buyReady
            ? "Price is touching or trading below the lower Bollinger Band, so this coin is eligible for a bounce entry."
            : proximityBuy
              ? `Price is within ${formatNumber((proximity ?? 0) * 100, 0)}% of the band width from the lower band, which is inside the smaller proximity-buy zone.`
              : "This strategy waits for price to reach the lower band for entries or the upper/middle band conditions for exits.",
      buyRule: "BUY executes when price touches or pierces the lower Bollinger Band. If price is merely within the closest 20% of band width to the lower band, the strategy can still open a smaller position.",
      sellRule: "SELL executes when price reaches the upper band, or when price drops back below the middle band after entry.",
      details: [
        { label: "Current price", value: formatNumber(currentPrice, 2) },
        { label: "Lower band", value: formatNumber(currentBbLower, 2) },
        { label: "Middle band", value: formatNumber(currentBbMiddle, 2) },
        { label: "Upper band", value: formatNumber(currentBbUpper, 2) }
      ]
    };
  }

  const rsiVote =
    currentRsi == null
      ? 0
      : currentRsi < 20
        ? 1
        : currentRsi < 30
          ? 0.8
          : currentRsi < 40
            ? 0.3
            : currentRsi > 80
              ? -1
              : currentRsi > 70
                ? -0.8
                : currentRsi > 60
                  ? -0.3
                  : 0;
  const macdVote =
    previousMacd == null || previousSignal == null || currentMacd == null || currentSignal == null || currentHistogram == null || previousHistogram == null
      ? 0
      : previousMacd <= previousSignal && currentMacd > currentSignal
        ? 0.8
        : previousMacd >= previousSignal && currentMacd < currentSignal
          ? -0.8
          : currentMacd > currentSignal
            ? currentHistogram > previousHistogram ? 0.5 : 0.2
            : currentMacd < currentSignal
              ? Math.abs(currentHistogram) < Math.abs(previousHistogram) ? -0.2 : -0.5
              : 0;
  const smaVote =
    previousSmaShort == null || previousSmaLong == null || currentSmaShort == null || currentSmaLong == null
      ? 0
      : previousSmaShort - previousSmaLong <= 0 && currentSmaShort - currentSmaLong > 0
        ? 0.8
        : previousSmaShort - previousSmaLong >= 0 && currentSmaShort - currentSmaLong < 0
          ? -0.8
          : currentSmaShort > currentSmaLong
            ? Math.abs(currentSmaShort - currentSmaLong) > Math.abs(previousSmaShort - previousSmaLong) ? 0.5 : 0.2
            : currentSmaShort < currentSmaLong
              ? Math.abs(currentSmaShort - currentSmaLong) < Math.abs(previousSmaShort - previousSmaLong) ? -0.2 : -0.5
              : 0;
  const emaVote =
    previousEmaFast == null || previousEmaSlow == null || currentEmaFast == null || currentEmaSlow == null
      ? 0
      : currentEmaFast > currentEmaSlow
        ? Math.abs(currentEmaFast - currentEmaSlow) > Math.abs(previousEmaFast - previousEmaSlow) ? 0.5 : 0.2
        : currentEmaFast < currentEmaSlow
          ? Math.abs(currentEmaFast - currentEmaSlow) < Math.abs(previousEmaFast - previousEmaSlow) ? -0.2 : -0.5
          : 0;
  const volumeVote =
    currentVolumeRatio == null || currentPrice == null || previousClose == null
      ? 0
      : currentVolumeRatio > 1.5 && currentPrice > previousClose
        ? 0.8
        : currentVolumeRatio > 1.5 && currentPrice < previousClose
          ? -0.8
          : currentVolumeRatio > 1 && currentPrice > previousClose
            ? 0.3
            : currentVolumeRatio > 1 && currentPrice < previousClose
              ? -0.3
              : 0;
  const volumeDampening = currentVolumeRatio != null && currentVolumeRatio < 0.5 ? 0.7 : 1;
  const visibleScore =
    (0.2 * rsiVote + 0.2 * macdVote + 0.1 * smaVote + 0.1 * emaVote + 0.25 * volumeVote) * volumeDampening;
  const confidenceGate = typeof config?.confidence_gate === "number" ? config.confidence_gate : 0.35;
  const visibleDirection = visibleScore > 0 ? "bullish" : visibleScore < 0 ? "bearish" : "flat";
  const signalReady = Math.abs(visibleScore) >= confidenceGate;

  return {
    statusLabel: signalReady ? `${visibleDirection === "bearish" ? "SELL" : "BUY"} candidate` : "Waiting for composite edge",
    tone: signalReady ? "accent" : "neutral",
    summary: signalReady
      ? `The visible composite inputs are ${visibleDirection} with an estimated score of ${formatSignedNumber(visibleScore, 3)}. Final execution still depends on the engine's market-quality, regime, structure, AI, and exit gates.`
      : `The visible composite inputs are currently ${visibleDirection} with an estimated score of ${formatSignedNumber(visibleScore, 3)}, which is still below the configured confidence gate of ${formatNumber(confidenceGate, 2)}.`,
    buyRule: "BUY executes only when the weighted composite turns decisively bullish and the engine also passes its quality, confidence, regime, and validation gates.",
    sellRule: "SELL executes when the composite and exit logic turn bearish enough for an open position, including hybrid exit checks such as reversal or managed stop logic.",
    details: [
      { label: "Visible score", value: formatSignedNumber(visibleScore, 3) },
      { label: "RSI", value: formatNumber(currentRsi, 1) },
      { label: "MACD gap", value: formatSignedNumber(currentMacd != null && currentSignal != null ? currentMacd - currentSignal : null, 3) },
      { label: "Volume ratio", value: formatNumber(currentVolumeRatio, 2) }
    ],
    note: "This page can estimate the visible technical setup, but the hybrid strategy also uses structure, market-quality, regime, ATR sizing, and AI validation that are not fully exposed here."
  };
}

type StrategyDetailClientProps = {
  strategy: StrategyWithStats;
  positions: Position[];
  trades: Trade[];
  summary: TradeSummary;
  equity: EquityPoint[];
  candles: Candle[];
  chartSymbol: string;
  chartInterval: string;
  indicators: MarketIndicatorsResponse;
};

export function StrategyDetailClient(props: StrategyDetailClientProps) {
  const { strategy, positions, trades, summary, equity, candles, chartSymbol, chartInterval, indicators } = props;
  const router = useRouter();
  const live = useLiveFeed();
  const [isPending, startTransition] = useTransition();
  const [executionMessage, setExecutionMessage] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState<AIPreviewResponse | null>(null);

  const strategyType = useMemo<StrategyType>(() => {
    const candidate = strategy.config_json?.strategy_type;
    return typeof candidate === "string" && candidate in STRATEGY_TYPE_META
      ? (candidate as StrategyType)
      : "hybrid_composite";
  }, [strategy.config_json]);

  const indicatorDisplay = useMemo(
    () => buildStrategyIndicatorDisplay(strategyType, indicators),
    [strategyType, indicators]
  );

  const executionMode = strategy.execution_mode ?? "single_symbol";
  const dailyPicks = strategy.daily_picks ?? [];
  const actualPickCount = dailyPicks.length;
  const targetPickCount = strategy.top_pick_count ?? 0;
  const focusSymbol = strategy.focus_symbol ?? chartSymbol;
  const openExposureBySymbol = strategy.open_exposure_by_symbol ?? {};
  const lastCandle = candles[candles.length - 1];
  const livePrice = live.latestPriceBySymbol[chartSymbol] ?? lastCandle?.close ?? null;

  const derivedPositions = useMemo(() => {
    return positions.map((position) => {
      const currentPrice = live.latestPriceBySymbol[position.symbol] ?? position.current_price ?? null;
      return {
        ...position,
        current_price: currentPrice,
        unrealized_pnl:
          currentPrice != null
            ? (currentPrice - position.entry_price) * position.quantity - position.entry_fee
            : position.unrealized_pnl
      };
    });
  }, [live.latestPriceBySymbol, positions]);

  const chartPosition = useMemo(
    () => derivedPositions.find((position) => position.symbol === chartSymbol) ?? null,
    [chartSymbol, derivedPositions]
  );
  const previousClose = candles.length > 1 ? candles[candles.length - 2]?.close ?? null : null;
  const executionGuide = useMemo(
    () =>
      buildExecutionGuide({
        strategyType,
        indicators,
        currentPrice: livePrice,
        previousClose,
        hasPosition: chartPosition != null,
        config: strategy.config_json
      }),
    [chartPosition, indicators, livePrice, previousClose, strategy.config_json, strategyType]
  );

  const statusLine = [
    `Chart ${chartSymbol}`,
    `Interval ${chartInterval}`,
    livePrice != null ? `Live ${livePrice.toFixed(2)}` : null,
    strategy.ai_last_decision_status ? `AI ${strategy.ai_last_decision_status}` : null,
    strategy.selection_date ? `Selection ${strategy.selection_date}` : null,
    strategy.ai_last_provider || strategy.ai_provider
      ? `Provider ${strategy.ai_last_provider || strategy.ai_provider}`
      : null,
    executionMessage ? `Response ${executionMessage}` : null
  ]
    .filter(Boolean)
    .join(" · ");

  const exposureLine = Object.entries(openExposureBySymbol)
    .map(([symbol, value]) => `${symbol} ${value.toFixed(2)}`)
    .join(" · ");

  const runManualExecution = (force: boolean) => {
    startTransition(async () => {
      try {
        const result = await executeStrategy(strategy.id, force);
        const nextSummary = result?.summary;
        if (nextSummary && typeof nextSummary.executed === "number") {
          setExecutionMessage(
            `Cycle complete: ${nextSummary.executed} trades, ${nextSummary.hold ?? 0} holds, ${nextSummary.skipped ?? 0} skipped`
          );
        } else {
          setExecutionMessage(result?.reason ?? result?.status ?? "Execution complete");
        }
        router.refresh();
      } catch (error) {
        setExecutionMessage(error instanceof Error ? error.message : "Execution failed");
      }
    });
  };

  const runAiPreview = async () => {
    setAiLoading(true);
    setAiResult(null);
    try {
      const result = await aiPreview(strategy.id);
      setAiResult(result);
      router.refresh();
    } catch (error) {
      setAiResult({
        status: "error",
        action: null,
        confidence: null,
        reason: null,
        raw_response: null,
        usage: null,
        error: error instanceof Error ? error.message : "AI call failed",
        strategy_key: "",
        preview_only: true
      });
    } finally {
      setAiLoading(false);
    }
  };

  const actionColor = (action: string | null) => {
    if (!action) return "text-slate-600";
    if (action === "BUY") return "text-emerald-700";
    if (action === "SELL") return "text-red-700";
    return "text-amber-700";
  };

  return (
    <div className="page-stage">
      <PageHeader
        title={strategy.name}
        actions={
          <>
            <button
              type="button"
              onClick={runAiPreview}
              disabled={aiLoading || isPending}
              className={buttonClassName("secondary", "md")}
            >
              {aiLoading ? "Thinking..." : "Ask AI"}
            </button>
            <button
              type="button"
              onClick={() => runManualExecution(false)}
              disabled={isPending}
              className={buttonClassName("primary", "md")}
            >
              Manual execute
            </button>
            <button
              type="button"
              onClick={() => runManualExecution(true)}
              disabled={isPending}
              className={buttonClassName("secondary", "md")}
            >
              Force execute
            </button>
          </>
        }
      />

      <section className="space-y-3">
        <MetricStrip
          items={[
            {
              label: "Mode",
              value: executionMode === "multi_coin_shared_wallet" ? "Shared Wallet" : chartSymbol
            },
            { label: "Focus", value: focusSymbol },
            {
              label: "Picks",
              value: targetPickCount > 0 ? `${actualPickCount}/${targetPickCount}` : actualPickCount
            },
            { label: "AI", value: strategy.ai_enabled ? "Enabled" : "Disabled" }
          ]}
        />
        <p className="text-sm leading-6 text-slate-600">{statusLine || "No recent execution status available."}</p>
        {Object.keys(openExposureBySymbol).length ? (
          <div className="flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <span>Exposure</span>
            {Object.entries(openExposureBySymbol).map(([symbol, value], i, arr) => (
              <span key={symbol} className="inline-flex items-center gap-1">
                <CoinIcon symbol={symbol} size={16} />
                {symbol} {value.toFixed(2)}
                {i < arr.length - 1 ? "·" : ""}
              </span>
            ))}
          </div>
        ) : null}
      </section>

      <Surface className="p-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 space-y-2">
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-400">
              Execution Details
            </p>
            <div className="space-y-1">
              <h2 className="text-lg font-semibold text-slate-900">
                When {chartSymbol} will trade
              </h2>
              <p className="max-w-3xl text-sm leading-6 text-slate-600">{executionGuide.summary}</p>
            </div>
          </div>
          <span
            className={[
              "inline-flex w-fit items-center rounded-md px-3 py-1 text-xs font-semibold",
              executionGuide.tone === "success"
                ? "bg-emerald-50 text-emerald-700"
                : executionGuide.tone === "warning"
                  ? "bg-amber-50 text-amber-700"
                  : executionGuide.tone === "accent"
                    ? "bg-blue-50 text-blue-700"
                    : "bg-slate-100 text-slate-700"
            ].join(" ")}
          >
            {executionGuide.statusLabel}
          </span>
        </div>

        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-emerald-100 bg-emerald-50/60 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-emerald-700">Buy trigger</p>
            <p className="mt-2 text-sm leading-6 text-emerald-950">{executionGuide.buyRule}</p>
          </div>
          <div className="rounded-xl border border-red-100 bg-red-50/70 p-4">
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-red-700">Sell trigger</p>
            <p className="mt-2 text-sm leading-6 text-red-950">{executionGuide.sellRule}</p>
          </div>
        </div>

        <dl className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {executionGuide.details.map((detail) => (
            <div key={detail.label} className="rounded-xl border border-slate-200/70 bg-slate-50 px-4 py-3">
              <dt className="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-400">
                {detail.label}
              </dt>
              <dd className="mt-1 text-sm font-semibold text-slate-900">{detail.value}</dd>
            </div>
          ))}
        </dl>

        {executionGuide.note ? (
          <p className="mt-4 text-sm leading-6 text-slate-500">{executionGuide.note}</p>
        ) : null}
      </Surface>

      {aiResult ? (
        <Surface className="overflow-hidden p-0">
          <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
            <div className="flex flex-wrap items-center gap-3">
              <span className="text-sm font-semibold text-slate-900">AI Preview</span>
              <span className={`text-lg font-bold ${actionColor(aiResult.action)}`}>
                {aiResult.action || aiResult.status?.toUpperCase()}
              </span>
              {aiResult.confidence != null ? (
                <span className="text-xs text-slate-500">
                  {(aiResult.confidence * 100).toFixed(0)}% confidence
                </span>
              ) : null}
              <span className="text-xs text-slate-500">Preview only</span>
            </div>
            <button
              onClick={() => setAiResult(null)}
              className="text-slate-400 transition hover:text-slate-700"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>
          </div>

          <div className="space-y-4 p-6">
            {aiResult.reason ? (
              <div>
                <p className="mb-1 text-xs uppercase tracking-[0.12em] text-slate-500">AI reasoning</p>
                <p className="text-sm leading-relaxed text-slate-900">{aiResult.reason}</p>
              </div>
            ) : null}

            {aiResult.error ? <p className="text-sm text-red-700">{aiResult.error}</p> : null}

            {aiResult.usage ? (
              <p className="flex flex-wrap gap-4 text-xs text-slate-500">
                <span>Provider: {aiResult.usage.provider}</span>
                <span>Model: {aiResult.usage.model}</span>
                <span>Tokens: {aiResult.usage.total_tokens.toLocaleString()}</span>
                <span>Cost: ${aiResult.usage.estimated_cost_usdt.toFixed(4)}</span>
                <span>Strategy: {aiResult.strategy_key}</span>
              </p>
            ) : null}

            {aiResult.raw_response ? (
              <details className="group">
                <summary className="cursor-pointer text-xs text-slate-500 transition hover:text-slate-700">
                  Show raw AI response
                </summary>
                <pre className="mt-2 max-h-40 overflow-auto bg-slate-50 p-3 text-xs text-slate-600">
                  {aiResult.raw_response}
                </pre>
              </details>
            ) : null}
          </div>
        </Surface>
      ) : null}

      <section className="grid gap-8 xl:grid-cols-[minmax(0,1.2fr)_20rem]">
        <div className="space-y-6">
          <PriceChart
            title={`${chartSymbol} ${chartInterval} Chart`}
            candles={candles}
            trades={trades.filter((trade) => trade.symbol === chartSymbol)}
            overlays={indicatorDisplay.overlays}
          />
          <StrategyIndicatorPanels
            panels={indicatorDisplay.panels}
            activeLabels={indicatorDisplay.activeLabels}
          />
        </div>
        <WalletSummary strategy={strategy} summary={summary} />
      </section>

      <section className="space-y-8">
        <div className="space-y-3">
          <h2 className="text-lg font-semibold text-slate-900">Performance and activity</h2>
          <PriceChart title="Equity Curve" candles={[]} equity={equity} mode="equity" shell={false} />
        </div>

        <OpenPositions positions={derivedPositions} />
        <TradeLog trades={trades} />

        <details className="border-t border-slate-200 pt-4">
          <summary className="cursor-pointer text-sm font-medium text-slate-900">
            AI telemetry
          </summary>
          <div className="mt-4">
            <AICallLog strategy={strategy} executionMessage={executionMessage} />
          </div>
        </details>
      </section>
    </div>
  );
}
