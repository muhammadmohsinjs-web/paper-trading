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
import { MetricStrip, PageHeader, Surface, buttonClassName } from "@/components/ui";
import { STRATEGY_TYPE_META } from "@/lib/types";
import type {
  Candle,
  EquityPoint,
  MarketIndicatorsResponse,
  Position,
  StrategyWithStats,
  Trade,
  TradeSummary,
  StrategyType
} from "@/lib/types";

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
        {exposureLine ? <p className="text-sm text-slate-500">Exposure {exposureLine}</p> : null}
      </section>

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
