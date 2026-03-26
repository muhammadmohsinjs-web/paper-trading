"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { formatCurrency, formatPercent } from "@/lib/format";
import { toggleStrategy } from "@/lib/api";
import { STRATEGY_TYPE_META, type StrategyType, type StrategyWithStats } from "@/lib/types";

export function StrategyCard({ strategy }: { strategy: StrategyWithStats }) {
  const router = useRouter();
  const [toggling, setToggling] = useState(false);
  const combinedPnl = strategy.total_pnl + (strategy.has_open_position ? (strategy.unrealized_pnl ?? 0) : 0);
  const pnlAccent = combinedPnl >= 0 ? "text-rise" : "text-fall";
  const dailyPicks = strategy.daily_picks ?? [];
  const executionMode = strategy.execution_mode ?? "single_symbol";
  const primarySymbol = strategy.primary_symbol ?? "BTCUSDT";
  const openPositionsCount = strategy.open_positions_count ?? 0;

  const strategyType = (strategy.config_json?.strategy_type as StrategyType) || "sma_crossover";
  const meta = STRATEGY_TYPE_META[strategyType] || STRATEGY_TYPE_META.sma_crossover;
  const pickSummary = dailyPicks.slice(0, 3).map((pick) => pick.symbol).join(" · ");
  const exposureSummary = Object.entries(strategy.open_exposure_by_symbol ?? {})
    .slice(0, 2)
    .map(([symbol, value]) => `${symbol} ${formatCurrency(value)}`)
    .join(" · ");

  async function handleToggle(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (toggling) return;
    setToggling(true);
    try {
      await toggleStrategy(strategy.id, !strategy.is_active);
      router.refresh();
    } catch {
      // Silently fail — will reflect on next refresh
    } finally {
      setToggling(false);
    }
  }

  return (
    <Link
      href={`/strategies/${strategy.id}`}
      className="panel group block overflow-hidden p-0 transition hover:-translate-y-1 hover:border-gold/30"
    >
      <div className="grid gap-5 border-b border-white/6 px-5 py-5 xl:grid-cols-[minmax(0,1.2fr),auto] xl:items-start">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`inline-flex rounded-full border px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.18em] ${meta.color}`}
            >
              {meta.label}
            </span>
            {strategy.ai_enabled ? (
              <span className="inline-flex rounded-full border border-gold/30 bg-gold/10 px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.18em] text-gold">
                AI Review
              </span>
            ) : null}
            <span className="inline-flex rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.18em] text-mist/65">
              {executionMode === "multi_coin_shared_wallet" ? "Shared Wallet" : primarySymbol}
            </span>
          </div>

          <div className="mt-4 flex min-w-0 flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
            <div className="min-w-0">
              <h3 className="text-2xl font-semibold text-sand">{strategy.name}</h3>
              <p className="mt-2 max-w-2xl break-words text-sm leading-6 text-mist/58">
                {strategy.description || meta.description}
              </p>
            </div>

            <div className="flex min-w-0 flex-wrap gap-2 text-xs uppercase tracking-[0.16em] text-mist/54">
              <span className="rounded-full border border-white/10 bg-black/15 px-3 py-1.5">
                Focus {strategy.focus_symbol ?? primarySymbol}
              </span>
              <span className="rounded-full border border-white/10 bg-black/15 px-3 py-1.5">
                {openPositionsCount} open
              </span>
              <span className="rounded-full border border-white/10 bg-black/15 px-3 py-1.5">
                Picks {dailyPicks.length || strategy.top_pick_count || 0}
              </span>
            </div>
          </div>

          <div className="mt-4 flex min-w-0 flex-col gap-2 text-sm text-mist/60 lg:flex-row lg:items-center lg:justify-between lg:gap-4">
            <p className="min-w-0 break-words">
              {executionMode === "multi_coin_shared_wallet" && pickSummary ? `Today: ${pickSummary}` : `Primary symbol: ${primarySymbol}`}
            </p>
            <p className="min-w-0 break-words lg:text-right">{exposureSummary || "No live exposure across the shared wallet"}</p>
          </div>
        </div>

        <div className="flex items-start justify-between gap-3 xl:flex-col xl:items-end">
          <button
            onClick={handleToggle}
            disabled={toggling}
            className={`shrink-0 rounded-full border px-3 py-1.5 text-xs uppercase tracking-[0.16em] transition ${
              strategy.is_active
                ? "border-rise/30 bg-rise/10 text-rise hover:bg-rise/20"
                : "border-white/10 bg-white/5 text-mist/50 hover:bg-white/10 hover:text-mist"
            } ${toggling ? "opacity-50" : ""}`}
          >
            {toggling ? "..." : strategy.is_active ? "Active" : "Paused"}
          </button>
          <p className="text-xs uppercase tracking-[0.16em] text-gold/72">
            {strategy.selection_date ? `Watchlist ${strategy.selection_date}` : "Watchlist pending"}
          </p>
        </div>
      </div>

      <div className="grid gap-4 px-5 py-5 md:grid-cols-4">
        <div className="rounded-[1.3rem] border border-white/8 bg-black/15 p-4">
          <p className="text-[10px] uppercase tracking-[0.2em] text-mist/42">Equity</p>
          <p className="mt-3 text-xl font-medium text-sand">{formatCurrency(strategy.total_equity)}</p>
        </div>
        <div className="rounded-[1.3rem] border border-white/8 bg-black/15 p-4">
          <p className="text-[10px] uppercase tracking-[0.2em] text-mist/42">Win Rate</p>
          <p className="mt-3 text-xl font-medium text-sand">{formatPercent(strategy.win_rate)}</p>
        </div>
        <div className="rounded-[1.3rem] border border-white/8 bg-black/15 p-4">
          <p className="text-[10px] uppercase tracking-[0.2em] text-mist/42">Total P&amp;L</p>
          <p className={`mt-3 text-xl font-medium ${pnlAccent}`}>{formatCurrency(combinedPnl)}</p>
        </div>
        <div className="rounded-[1.3rem] border border-white/8 bg-black/15 p-4">
          <p className="text-[10px] uppercase tracking-[0.2em] text-mist/42">Trades</p>
          <p className="mt-3 text-xl font-medium text-sand">{strategy.total_trades}</p>
        </div>
      </div>

      <div className="flex items-center justify-between px-5 pb-5 text-xs uppercase tracking-[0.16em] text-mist/42">
        <span>AI calls {strategy.ai_total_calls}</span>
        <span className="transition group-hover:text-gold">Open desk</span>
      </div>
    </Link>
  );
}
