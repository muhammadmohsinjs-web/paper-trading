import { formatCurrency, formatDateTime, formatPercent } from "@/lib/format";
import type { StrategyWithStats, TradeSummary } from "@/lib/types";
import { StatusPill } from "@/components/status-pill";

type WalletSummaryProps = {
  strategy: StrategyWithStats;
  summary: TradeSummary;
};

export function WalletSummary({ strategy, summary }: WalletSummaryProps) {
  return (
    <section className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
      <div className="rounded-[28px] border border-white/10 bg-panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.22em] text-mist/55">Wallet Summary</div>
            <h2 className="mt-2 text-3xl font-semibold text-sand">{strategy.name}</h2>
            <p className="mt-2 text-sm text-mist/70">
              {strategy.description || "No description provided."}
            </p>
          </div>
          <div className="flex flex-col gap-2">
            <StatusPill tone={strategy.is_active ? "rise" : "muted"}>
              {strategy.is_active ? "Active" : "Paused"}
            </StatusPill>
            {strategy.ai_enabled ? (
              <StatusPill tone="gold">{strategy.ai_last_decision_status || "AI enabled"}</StatusPill>
            ) : null}
          </div>
        </div>
        <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
          <div>
            <div className="text-sm text-mist/55">Initial</div>
            <div className="mt-1 text-xl font-medium">{formatCurrency(strategy.initial_balance_usdt)}</div>
          </div>
          <div>
            <div className="text-sm text-mist/55">Available</div>
            <div className="mt-1 text-xl font-medium">{formatCurrency(strategy.available_usdt)}</div>
          </div>
          <div>
            <div className="text-sm text-mist/55">Equity</div>
            <div className="mt-1 text-xl font-medium">{formatCurrency(strategy.total_equity)}</div>
          </div>
          <div>
            <div className="text-sm text-mist/55">Win Rate</div>
            <div className="mt-1 text-xl font-medium">{formatPercent(summary.win_rate)}</div>
          </div>
        </div>
      </div>
      <div className="rounded-[28px] border border-white/10 bg-panel/80 p-5">
        <div className="text-xs uppercase tracking-[0.22em] text-mist/55">AI Telemetry</div>
        <div className="mt-4 space-y-3 text-sm text-mist/75">
          <div className="flex items-center justify-between">
            <span>Model</span>
            <span className="text-sand">{strategy.ai_last_model || strategy.ai_model || "--"}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Total calls</span>
            <span className="text-sand">{strategy.ai_total_calls}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Total cost</span>
            <span className="text-sand">{formatCurrency(strategy.ai_total_cost_usdt)}</span>
          </div>
          <div className="flex items-center justify-between">
            <span>Last decision</span>
            <span className="text-sand">{strategy.ai_last_decision_status || "--"}</span>
          </div>
          <div className="border-t border-white/10 pt-3 text-xs text-mist/55">
            {strategy.ai_last_reasoning || "No AI reasoning recorded yet."}
          </div>
          <div className="text-xs text-mist/45">
            Last updated {formatDateTime(strategy.ai_last_decision_at)}
          </div>
        </div>
      </div>
    </section>
  );
}
