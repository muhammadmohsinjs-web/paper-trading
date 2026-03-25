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

  const strategyType = (strategy.config_json?.strategy_type as StrategyType) || "sma_crossover";
  const meta = STRATEGY_TYPE_META[strategyType] || STRATEGY_TYPE_META.sma_crossover;

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
      className="panel group flex h-full flex-col justify-between p-5 transition hover:-translate-y-1 hover:border-gold/30"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          {/* Strategy type badge */}
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex rounded-md border px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.15em] ${meta.color}`}
            >
              {meta.short}
            </span>
            {strategy.ai_enabled && (
              <span className="inline-flex rounded-md border border-gold/30 bg-gold/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.15em] text-gold">
                AI
              </span>
            )}
          </div>

          <h3 className="mt-2 text-lg font-semibold text-sand">{strategy.name}</h3>
          <p className="mt-1 text-xs leading-5 text-mist/55 line-clamp-2">
            {strategy.description || meta.description}
          </p>
        </div>

        {/* Active toggle */}
        <button
          onClick={handleToggle}
          disabled={toggling}
          className={`shrink-0 rounded-full border px-3 py-1 text-xs uppercase tracking-[0.15em] transition ${
            strategy.is_active
              ? "border-rise/30 bg-rise/10 text-rise hover:bg-rise/20"
              : "border-white/10 bg-white/5 text-mist/50 hover:bg-white/10 hover:text-mist"
          } ${toggling ? "opacity-50" : ""}`}
        >
          {toggling ? "..." : strategy.is_active ? "Active" : "Paused"}
        </button>
      </div>

      <div className="mt-5 grid grid-cols-2 gap-4 text-sm">
        <div>
          <p className="text-mist/45 text-xs">Equity</p>
          <p className="mt-0.5 text-lg font-medium text-sand">{formatCurrency(strategy.total_equity)}</p>
        </div>
        <div>
          <p className="text-mist/45 text-xs">Win Rate</p>
          <p className="mt-0.5 text-lg font-medium text-sand">{formatPercent(strategy.win_rate)}</p>
        </div>
        <div>
          <p className="text-mist/45 text-xs">Total P&L</p>
          <p className={`mt-0.5 text-lg font-medium ${pnlAccent}`}>{formatCurrency(combinedPnl)}</p>
        </div>
        <div>
          <p className="text-mist/45 text-xs">Trades</p>
          <p className="mt-0.5 text-lg font-medium text-sand">{strategy.total_trades}</p>
        </div>
      </div>

      <div className="mt-5 flex items-center justify-between border-t border-white/6 pt-3 text-xs text-mist/45">
        <span>AI Calls: {strategy.ai_total_calls}</span>
        <span className="transition group-hover:text-gold">Open strategy</span>
      </div>
    </Link>
  );
}
