import Link from "next/link";
import { formatCurrency, formatPercent } from "@/lib/format";
import type { StrategyWithStats } from "@/lib/types";

export function StrategyCard({ strategy }: { strategy: StrategyWithStats }) {
  const pnlAccent = strategy.total_pnl >= 0 ? "text-rise" : "text-fall";

  return (
    <Link
      href={`/strategies/${strategy.id}`}
      className="panel group flex h-full flex-col justify-between p-5 transition hover:-translate-y-1 hover:border-gold/30"
    >
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-mist/50">
            {strategy.ai_enabled ? strategy.ai_strategy_key ?? "AI" : "Rule Based"}
          </p>
          <h3 className="mt-2 text-xl font-semibold text-sand">{strategy.name}</h3>
          <p className="mt-2 text-sm leading-6 text-mist/65">
            {strategy.description || "No description provided."}
          </p>
        </div>
        <span
          className={`rounded-full border px-3 py-1 text-xs uppercase tracking-[0.2em] ${
            strategy.is_active
              ? "border-rise/30 bg-rise/10 text-rise"
              : "border-white/10 bg-white/5 text-mist/60"
          }`}
        >
          {strategy.is_active ? "Active" : "Paused"}
        </span>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-4 text-sm">
        <div>
          <p className="text-mist/50">Equity</p>
          <p className="mt-1 text-lg font-medium text-sand">{formatCurrency(strategy.total_equity)}</p>
        </div>
        <div>
          <p className="text-mist/50">Win Rate</p>
          <p className="mt-1 text-lg font-medium text-sand">{formatPercent(strategy.win_rate)}</p>
        </div>
        <div>
          <p className="text-mist/50">P&L</p>
          <p className={`mt-1 text-lg font-medium ${pnlAccent}`}>{formatCurrency(strategy.total_pnl)}</p>
        </div>
        <div>
          <p className="text-mist/50">Trades</p>
          <p className="mt-1 text-lg font-medium text-sand">{strategy.total_trades}</p>
        </div>
      </div>

      <div className="mt-6 flex items-center justify-between border-t border-white/8 pt-4 text-xs text-mist/55">
        <span>AI Calls: {strategy.ai_total_calls}</span>
        <span className="transition group-hover:text-gold">Open strategy</span>
      </div>
    </Link>
  );
}
