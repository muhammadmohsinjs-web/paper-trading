"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { LocalDateTime } from "@/components/local-date-time";
import { LivePrice } from "@/components/live-price";
import { PriceChart } from "@/components/price-chart";
import { OpenPositions } from "@/components/open-positions";
import { TradeLog } from "@/components/trade-log";
import { WalletSummary } from "@/components/wallet-summary";
import { AICallLog } from "@/components/ai-call-log";
import { useLiveFeed } from "@/hooks/use-live-feed";
import { executeStrategy, aiPreview, type AIPreviewResponse } from "@/lib/api";
import type {
  Candle,
  EquityPoint,
  Position,
  StrategyWithStats,
  Trade,
  TradeSummary
} from "@/lib/types";

type StrategyDetailClientProps = {
  strategy: StrategyWithStats;
  positions: Position[];
  trades: Trade[];
  summary: TradeSummary;
  equity: EquityPoint[];
  candles: Candle[];
  chartSymbol: string;
};

export function StrategyDetailClient(props: StrategyDetailClientProps) {
  const { strategy, positions, trades, summary, equity, candles, chartSymbol } = props;
  const router = useRouter();
  const live = useLiveFeed();
  const [isPending, startTransition] = useTransition();
  const [executionMessage, setExecutionMessage] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState<AIPreviewResponse | null>(null);
  const executionMode = strategy.execution_mode ?? "single_symbol";
  const dailyPicks = strategy.daily_picks ?? [];
  const openExposureBySymbol = strategy.open_exposure_by_symbol ?? {};
  const maxConcurrentPositions = strategy.max_concurrent_positions ?? 2;
  const portfolioRiskStatus = (strategy.portfolio_risk_status ?? {}) as {
    exposure_pct?: number;
    drawdown_pct?: number;
    limits?: {
      max_exposure_pct?: number;
      portfolio_drawdown_halt_pct?: number;
    };
  };
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
            : position.unrealized_pnl,
      };
    });
  }, [live.latestPriceBySymbol, positions]);

  const runManualExecution = (force: boolean) => {
    startTransition(async () => {
      try {
        const result = await executeStrategy(strategy.id, force);
        const summary = result?.summary;
        if (summary && typeof summary.executed === "number") {
          setExecutionMessage(
            `Cycle complete: ${summary.executed} trades, ${summary.hold ?? 0} holds, ${summary.skipped ?? 0} skipped`
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
        preview_only: true,
      });
    } finally {
      setAiLoading(false);
    }
  };

  const actionColor = (action: string | null) => {
    if (!action) return "text-mist";
    if (action === "BUY") return "text-rise";
    if (action === "SELL") return "text-fall";
    return "text-gold";
  };

  return (
    <div className="space-y-6">
      <section className="panel overflow-hidden p-0">
        <div className="grid gap-0 xl:grid-cols-[1.12fr,0.88fr]">
          <div className="min-w-0 border-b border-white/6 px-6 py-6 xl:border-b-0 xl:border-r">
            <div className="flex flex-wrap gap-2">
              <span className="rounded-full border border-gold/20 bg-gold/10 px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-gold">
                {strategy.ai_enabled ? "AI-Guided Strategy" : "Rule Strategy"}
              </span>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-mist/65">
                {executionMode === "multi_coin_shared_wallet" ? "Shared Wallet" : chartSymbol}
              </span>
              <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-mist/65">
                Focus {strategy.focus_symbol ?? chartSymbol}
              </span>
            </div>

            <h2 className="mt-4 text-4xl font-semibold text-sand">{strategy.name}</h2>
            <p className="mt-3 max-w-2xl break-words text-sm leading-7 text-mist/65">
              {strategy.description || "No strategy description available."}
            </p>

            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              <div className="rounded-[1.4rem] border border-white/8 bg-black/15 p-4">
                <p className="text-[10px] uppercase tracking-[0.2em] text-mist/45">Chart Symbol</p>
                <p className="mt-3 text-xl font-semibold text-sand">{chartSymbol}</p>
              </div>
              <div className="rounded-[1.4rem] border border-white/8 bg-black/15 p-4">
                <p className="text-[10px] uppercase tracking-[0.2em] text-mist/45">Live Price</p>
                <p className="mt-3 text-xl font-semibold text-sand">
                  <LivePrice price={livePrice} variant="inline" className="text-sand" />
                </p>
              </div>
              <div className="rounded-[1.4rem] border border-white/8 bg-black/15 p-4">
                <p className="text-[10px] uppercase tracking-[0.2em] text-mist/45">Last AI Status</p>
                <p className="mt-3 text-xl font-semibold text-sand">{strategy.ai_last_decision_status ?? "--"}</p>
              </div>
            </div>

            <div className="mt-5 flex flex-wrap gap-3 text-xs uppercase tracking-[0.16em] text-mist/55">
              <span>
                Last decision <LocalDateTime value={strategy.ai_last_decision_at} />
              </span>
              <span>Provider {strategy.ai_last_provider || strategy.ai_provider || "--"}</span>
              <span>Selection {strategy.selection_date ?? "--"}</span>
            </div>
          </div>

          <div className="min-w-0 px-6 py-6">
            <p className="text-xs uppercase tracking-[0.24em] text-gold">Decision Controls</p>
            <h3 className="mt-3 text-2xl font-semibold text-sand">Run The Desk</h3>
            <p className="mt-2 break-words text-sm leading-6 text-mist/62">
              Trigger a manual cycle, force an evaluation pass, or ask AI to produce a read on the current setup.
            </p>

            <div className="mt-5 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={runAiPreview}
                disabled={aiLoading || isPending}
                className="rounded-full border border-purple-400/40 bg-purple-400/10 px-4 py-2 text-sm text-purple-400 transition hover:bg-purple-400/15 disabled:opacity-50"
              >
                {aiLoading ? (
                  <span className="flex items-center gap-2">
                    <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-purple-400/30 border-t-purple-400" />
                    AI Thinking...
                  </span>
                ) : (
                  "Ask AI"
                )}
              </button>
              <button
                type="button"
                onClick={() => runManualExecution(false)}
                disabled={isPending}
                className="rounded-full border border-gold/40 bg-gold/10 px-4 py-2 text-sm text-gold transition hover:bg-gold/15 disabled:opacity-50"
              >
                Manual Execute
              </button>
              <button
                type="button"
                onClick={() => runManualExecution(true)}
                disabled={isPending}
                className="rounded-full border border-white/10 px-4 py-2 text-sm text-mist transition hover:border-rise/40 hover:text-rise disabled:opacity-50"
              >
                Force Execute
              </button>
            </div>

            <div className="mt-5 rounded-[1.5rem] border border-white/8 bg-black/15 p-4">
              <p className="text-[10px] uppercase tracking-[0.2em] text-mist/45">Execution Response</p>
              <p className="mt-3 break-words text-sm leading-6 text-sand">
                {executionMessage ?? "Trigger a manual cycle or ask AI for its market analysis."}
              </p>
            </div>

            {executionMode === "multi_coin_shared_wallet" ? (
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <div className="rounded-[1.4rem] border border-white/8 bg-white/[0.03] p-4">
                  <p className="text-[10px] uppercase tracking-[0.2em] text-mist/45">Watchlist</p>
                  <p className="mt-3 break-words text-sm leading-6 text-sand">
                    {dailyPicks.map((pick) => pick.symbol).join(" · ") || "No picks persisted yet"}
                  </p>
                </div>
                <div className="rounded-[1.4rem] border border-white/8 bg-white/[0.03] p-4">
                  <p className="text-[10px] uppercase tracking-[0.2em] text-mist/45">Exposure</p>
                  <p className="mt-3 break-words text-sm leading-6 text-sand">
                    {Object.entries(openExposureBySymbol)
                      .map(([symbol, value]) => `${symbol} $${value.toFixed(2)}`)
                      .join(" · ") || "No live exposure"}
                  </p>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </section>

      {/* AI Preview Result Panel */}
      {aiResult && (
        <section className="panel overflow-hidden">
          <div className="flex items-center justify-between border-b border-white/6 px-6 py-4">
            <div className="flex items-center gap-3">
              <span className="text-xs uppercase tracking-[0.24em] text-purple-400">AI Preview</span>
              <span className={`text-lg font-bold ${actionColor(aiResult.action)}`}>
                {aiResult.action || aiResult.status?.toUpperCase()}
              </span>
              {aiResult.confidence != null && (
                <span className="rounded-md bg-white/5 px-2 py-0.5 text-xs text-mist/70">
                  {(aiResult.confidence * 100).toFixed(0)}% confidence
                </span>
              )}
              <span className="rounded-md bg-white/5 px-2 py-0.5 text-xs text-mist/50">
                Preview only — no trade placed
              </span>
            </div>
            <button
              onClick={() => setAiResult(null)}
              className="text-mist/40 transition hover:text-mist"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </button>
          </div>

          <div className="space-y-4 p-6">
            {/* Reason */}
            {aiResult.reason && (
              <div>
                <p className="mb-1 text-xs uppercase tracking-[0.2em] text-mist/40">AI Reasoning</p>
                <p className="text-sm leading-relaxed text-sand/90">{aiResult.reason}</p>
              </div>
            )}

            {/* Error */}
            {aiResult.error && (
              <div className="rounded-lg border border-fall/20 bg-fall/5 px-4 py-3">
                <p className="text-sm text-fall">{aiResult.error}</p>
              </div>
            )}

            {/* Usage stats */}
            {aiResult.usage && (
              <div className="flex flex-wrap gap-4 text-xs text-mist/50">
                <span>Provider: {aiResult.usage.provider}</span>
                <span>Model: {aiResult.usage.model}</span>
                <span>Tokens: {aiResult.usage.total_tokens.toLocaleString()}</span>
                <span>Cost: ${aiResult.usage.estimated_cost_usdt.toFixed(4)}</span>
                <span>Strategy: {aiResult.strategy_key}</span>
              </div>
            )}

            {/* Raw response (collapsible) */}
            {aiResult.raw_response && (
              <details className="group">
                <summary className="cursor-pointer text-xs text-mist/40 transition hover:text-mist/60">
                  Show raw AI response
                </summary>
                <pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-black/30 p-3 text-xs text-mist/60">
                  {aiResult.raw_response}
                </pre>
              </details>
            )}
          </div>
        </section>
      )}

      <WalletSummary strategy={strategy} summary={summary} />

      {executionMode === "multi_coin_shared_wallet" ? (
        <section className="panel p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-gold">Portfolio Context</p>
              <h3 className="mt-2 text-xl font-semibold text-sand">Daily Picks And Exposure</h3>
              <p className="mt-2 text-sm text-mist/60">
                Entry universe for {strategy.selection_date ?? "today"} with a shared wallet and max {maxConcurrentPositions} positions.
              </p>
            </div>
            <div className="text-sm text-mist/60">
              Focus chart: <span className="text-sand">{chartSymbol}</span>
            </div>
          </div>
          <div className="mt-5 grid gap-4 lg:grid-cols-3">
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-mist/45">Top 5 Picks</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {dailyPicks.map((pick) => (
                  <div key={pick.symbol} className="rounded-xl border border-gold/20 bg-gold/10 px-3 py-2 text-sm text-gold/90">
                    #{pick.rank} {pick.symbol}
                  </div>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-mist/45">Open Exposure</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {Object.entries(openExposureBySymbol).length > 0 ? (
                  Object.entries(openExposureBySymbol).map(([symbol, value]) => (
                    <div key={symbol} className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm text-sand">
                      {symbol} ${value.toFixed(2)}
                    </div>
                  ))
                ) : (
                  <div className="text-sm text-mist/55">No live exposure.</div>
                )}
              </div>
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.18em] text-mist/45">Risk Status</p>
              <div className="mt-3 space-y-2 rounded-[1.5rem] border border-white/8 bg-black/15 p-4 text-sm text-mist/68">
                <div className="flex items-center justify-between">
                  <span>Exposure</span>
                  <span className="text-sand">
                    {portfolioRiskStatus.exposure_pct != null
                      ? `${portfolioRiskStatus.exposure_pct.toFixed(2)}%`
                      : "--"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Drawdown</span>
                  <span className="text-sand">
                    {portfolioRiskStatus.drawdown_pct != null
                      ? `${portfolioRiskStatus.drawdown_pct.toFixed(2)}%`
                      : "--"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Exposure limit</span>
                  <span className="text-sand">
                    {portfolioRiskStatus.limits?.max_exposure_pct != null
                      ? `${portfolioRiskStatus.limits.max_exposure_pct}%`
                      : "--"}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Drawdown halt</span>
                  <span className="text-sand">
                    {portfolioRiskStatus.limits?.portfolio_drawdown_halt_pct != null
                      ? `${portfolioRiskStatus.limits.portfolio_drawdown_halt_pct}%`
                      : "--"}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </section>
      ) : null}

      <div className="grid gap-6 xl:grid-cols-[1.2fr,0.8fr]">
        <PriceChart title={`${chartSymbol} Price Chart`} candles={candles} trades={trades.filter((trade) => trade.symbol === chartSymbol)} />
        <AICallLog strategy={strategy} executionMessage={executionMessage} />
      </div>

      <PriceChart title="Equity Curve" candles={[]} equity={equity} mode="equity" />
      <OpenPositions positions={derivedPositions} />
      <TradeLog trades={trades} />
    </div>
  );
}
