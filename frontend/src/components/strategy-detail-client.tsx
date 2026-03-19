"use client";

import { useMemo, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { LivePrice } from "@/components/live-price";
import { PriceChart } from "@/components/price-chart";
import { OpenPositions } from "@/components/open-positions";
import { TradeLog } from "@/components/trade-log";
import { WalletSummary } from "@/components/wallet-summary";
import { useLiveFeed } from "@/hooks/use-live-feed";
import { executeStrategy } from "@/lib/api";
import { formatCurrency, formatDateTime, formatNumber } from "@/lib/format";
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
          <div className="flex gap-3">
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
          <p className="text-sm text-mist/60">{executionMessage ?? strategy.ai_last_reasoning ?? "Awaiting decision."}</p>
        </div>
      </section>

      <WalletSummary strategy={strategy} summary={summary} />

      <div className="grid gap-6 xl:grid-cols-[1.2fr,0.8fr]">
        <PriceChart title="Price Chart" candles={candles} trades={trades} />
        <div className="panel grid gap-4 p-5">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-mist/50">AI Telemetry</p>
            <h3 className="mt-2 text-xl font-semibold text-sand">Decision Console</h3>
          </div>
          <div className="grid gap-3 rounded-[22px] border border-white/8 bg-black/10 p-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-mist/55">Provider</p>
                <p className="mt-2 text-sm text-sand">{strategy.ai_provider}</p>
              </div>
              <div>
                <p className="text-xs uppercase tracking-[0.18em] text-mist/55">Model</p>
                <p className="mt-2 text-sm text-sand">{strategy.ai_model || "--"}</p>
              </div>
            </div>
            <p className="text-xs text-mist/50">
              Controlled from `backend/.env`. Change `AI_PROVIDER` and `AI_MODEL`, then restart the backend.
            </p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="panel-soft p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-mist/55">Total Calls</p>
              <p className="mt-2 text-xl font-semibold text-sand">{strategy.ai_total_calls}</p>
            </div>
            <div className="panel-soft p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-mist/55">Total Cost</p>
              <p className="mt-2 text-xl font-semibold text-gold">{formatCurrency(strategy.ai_total_cost_usdt)}</p>
            </div>
            <div className="panel-soft p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-mist/55">Prompt Tokens</p>
              <p className="mt-2 text-xl font-semibold text-sand">{formatNumber(strategy.ai_total_prompt_tokens, 0)}</p>
            </div>
            <div className="panel-soft p-4">
              <p className="text-xs uppercase tracking-[0.22em] text-mist/55">Completion Tokens</p>
              <p className="mt-2 text-xl font-semibold text-sand">{formatNumber(strategy.ai_total_completion_tokens, 0)}</p>
            </div>
          </div>
        </div>
      </div>

      <PriceChart title="Equity Curve" candles={[]} equity={equity} mode="equity" />
      <OpenPositions positions={derivedPositions} />
      <TradeLog trades={trades} />
    </div>
  );
}
