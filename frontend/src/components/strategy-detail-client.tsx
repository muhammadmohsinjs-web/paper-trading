"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { LivePrice } from "@/components/live-price";
import { PriceChart } from "@/components/price-chart";
import { OpenPositions } from "@/components/open-positions";
import { TradeLog } from "@/components/trade-log";
import { WalletSummary } from "@/components/wallet-summary";
import { AICallLog } from "@/components/ai-call-log";
import { useLiveFeed } from "@/hooks/use-live-feed";
import { executeStrategy, aiPreview, type AIPreviewResponse } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
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
};

export function StrategyDetailClient(props: StrategyDetailClientProps) {
  const { strategy, positions, trades, summary, equity, candles } = props;
  const router = useRouter();
  const live = useLiveFeed();
  const [isPending, startTransition] = useTransition();
  const [executionMessage, setExecutionMessage] = useState<string | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiResult, setAiResult] = useState<AIPreviewResponse | null>(null);
  const lastCandle = candles[candles.length - 1];
  const livePrice = live.latestPriceBySymbol.BTCUSDT ?? lastCandle?.close ?? null;
  const derivedPositions = useMemo(() => {
    if (live.lastPositionEvent?.strategy_id !== strategy.id) {
      return positions;
    }
    if (!live.lastPositionEvent.has_position) {
      return [];
    }
    return [
      {
        id: "live-position",
        strategy_id: strategy.id,
        symbol: String(live.lastPositionEvent.symbol ?? "BTCUSDT"),
        side: "LONG",
        quantity: Number(live.lastPositionEvent.quantity ?? 0),
        entry_price: Number(live.lastPositionEvent.entry_price ?? 0),
        entry_fee: 0,
        opened_at: new Date().toISOString(),
        current_price: livePrice,
        unrealized_pnl:
          livePrice && live.lastPositionEvent.entry_price
            ? (livePrice - Number(live.lastPositionEvent.entry_price)) *
              Number(live.lastPositionEvent.quantity ?? 0)
            : null
      }
    ];
  }, [live.lastPositionEvent, livePrice, positions, strategy.id]);

  const runManualExecution = (force: boolean) => {
    startTransition(async () => {
      try {
        const result = await executeStrategy(strategy.id, force);
        setExecutionMessage(result?.reason ?? result?.status ?? "Execution complete");
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
      <section className="panel flex flex-col gap-5 p-6 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-gold">{strategy.ai_enabled ? "AI Strategy" : "Rule Strategy"}</p>
          <h2 className="mt-2 text-3xl font-semibold text-sand">{strategy.name}</h2>
          <p className="mt-2 max-w-2xl text-sm text-mist/65">
            {strategy.description || "No strategy description available."}
          </p>
          <div className="mt-4 flex flex-wrap gap-3 text-xs text-mist/55">
            <span>Last AI status: {strategy.ai_last_decision_status ?? "--"}</span>
            <span>Last decision: {formatDateTime(strategy.ai_last_decision_at)}</span>
            <span>Provider: {strategy.ai_last_provider || strategy.ai_provider}</span>
            <span className="flex items-center gap-2">
              <span>BTCUSDT:</span>
              <LivePrice price={livePrice} variant="inline" className="text-sand" />
            </span>
          </div>
        </div>

        <div className="flex flex-col items-start gap-3 lg:items-end">
          <div className="flex flex-wrap gap-3">
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
          <p className="text-sm text-mist/60">
            {executionMessage ?? "Trigger a manual cycle or ask AI for its market analysis."}
          </p>
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

      <div className="grid gap-6 xl:grid-cols-[1.2fr,0.8fr]">
        <PriceChart title="Price Chart" candles={candles} trades={trades} />
        <AICallLog strategy={strategy} executionMessage={executionMessage} />
      </div>

      <PriceChart title="Equity Curve" candles={[]} equity={equity} mode="equity" />
      <OpenPositions positions={derivedPositions} />
      <TradeLog trades={trades} />
    </div>
  );
}
