import { formatCurrency, formatDateTime, formatPercent } from "@/lib/format";
import type { StrategyWithStats, TradeSummary } from "@/lib/types";
import { StatusPill } from "@/components/status-pill";

type WalletSummaryProps = {
  strategy: StrategyWithStats;
  summary: TradeSummary;
};

export function WalletSummary({ strategy, summary }: WalletSummaryProps) {
  const executionMode = strategy.execution_mode ?? "single_symbol";
  const primarySymbol = strategy.primary_symbol ?? "BTCUSDT";
  const dailyPicks = strategy.daily_picks ?? [];
  const openPositionsCount = strategy.open_positions_count ?? 0;
  const exposureBySymbol = Object.entries(strategy.open_exposure_by_symbol ?? {});
  const riskStatus = (strategy.portfolio_risk_status ?? {}) as {
    exposure_pct?: number;
    drawdown_pct?: number;
    limits?: {
      max_exposure_pct?: number;
      portfolio_drawdown_halt_pct?: number;
    };
  };

  return (
    <section className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
      <div className="panel min-w-0 overflow-hidden p-0">
        <div className="border-b border-white/6 px-5 py-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="text-xs uppercase tracking-[0.22em] text-mist/55">Wallet Summary</div>
              <h2 className="mt-3 text-3xl font-semibold text-sand">{strategy.name}</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-mist/70">
                {strategy.description || "No description provided."}
              </p>
            </div>
            <div className="flex flex-col gap-2">
              <StatusPill tone={strategy.is_active ? "rise" : "muted"}>
                {strategy.is_active ? "Active" : "Paused"}
              </StatusPill>
              <StatusPill tone="muted">
                {executionMode === "multi_coin_shared_wallet" ? "Shared Wallet" : primarySymbol}
              </StatusPill>
              {strategy.ai_enabled ? (
                <StatusPill tone="gold">{strategy.ai_last_decision_status || "AI enabled"}</StatusPill>
              ) : null}
            </div>
          </div>
        </div>

        <div className="grid min-w-0 gap-4 px-5 py-5 lg:grid-cols-3">
          <div className="rounded-[1.4rem] border border-white/8 bg-black/15 p-4">
            <div className="text-[10px] uppercase tracking-[0.2em] text-mist/45">Capital</div>
            <div className="mt-4 space-y-3 text-sm text-mist/72">
              <div className="flex items-center justify-between">
                <span>Initial</span>
                <span className="text-sand">{formatCurrency(strategy.initial_balance_usdt)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Available</span>
                <span className="text-sand">{formatCurrency(strategy.available_usdt)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Total equity</span>
                <span className="text-sand">{formatCurrency(strategy.total_equity)}</span>
              </div>
            </div>
          </div>

          <div className="rounded-[1.4rem] border border-white/8 bg-black/15 p-4">
            <div className="text-[10px] uppercase tracking-[0.2em] text-mist/45">Performance</div>
            <div className="mt-4 space-y-3 text-sm text-mist/72">
              <div className="flex items-center justify-between">
                <span>Realized P&amp;L</span>
                <span className={strategy.total_pnl >= 0 ? "text-rise" : "text-fall"}>
                  {formatCurrency(strategy.total_pnl)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>Unrealized P&amp;L</span>
                <span
                  className={
                    strategy.has_open_position
                      ? (strategy.unrealized_pnl ?? 0) >= 0
                        ? "text-rise"
                        : "text-fall"
                      : "text-mist/40"
                  }
                >
                  {strategy.has_open_position ? formatCurrency(strategy.unrealized_pnl ?? 0) : "—"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>Win rate</span>
                <span className="text-sand">{formatPercent(summary.win_rate)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Open positions</span>
                <span className="text-sand">{openPositionsCount}</span>
              </div>
            </div>
          </div>

          <div className="rounded-[1.4rem] border border-white/8 bg-black/15 p-4">
            <div className="text-[10px] uppercase tracking-[0.2em] text-mist/45">Risk Envelope</div>
            <div className="mt-4 space-y-3 text-sm text-mist/72">
              <div className="flex items-center justify-between">
                <span>Exposure</span>
                <span className="text-sand">
                  {riskStatus.exposure_pct != null ? `${riskStatus.exposure_pct.toFixed(2)}%` : "--"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>Drawdown</span>
                <span className="text-sand">
                  {riskStatus.drawdown_pct != null ? `${riskStatus.drawdown_pct.toFixed(2)}%` : "--"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>Exposure limit</span>
                <span className="text-sand">
                  {riskStatus.limits?.max_exposure_pct != null ? `${riskStatus.limits.max_exposure_pct}%` : "--"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>Drawdown halt</span>
                <span className="text-sand">
                  {riskStatus.limits?.portfolio_drawdown_halt_pct != null
                    ? `${riskStatus.limits.portfolio_drawdown_halt_pct}%`
                    : "--"}
                </span>
              </div>
            </div>
          </div>
        </div>

        {(executionMode === "multi_coin_shared_wallet" && dailyPicks.length > 0) || exposureBySymbol.length ? (
          <div className="grid gap-4 border-t border-white/6 px-5 py-5 lg:grid-cols-2">
            <div>
              <div className="text-xs uppercase tracking-[0.22em] text-mist/55">Today&apos;s Picks</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {dailyPicks.length ? (
                  dailyPicks.map((pick) => (
                    <span
                      key={pick.symbol}
                      className="rounded-full border border-gold/20 bg-gold/10 px-3 py-1 text-xs text-gold/85"
                    >
                      #{pick.rank} {pick.symbol}
                    </span>
                  ))
                ) : (
                  <span className="text-sm text-mist/55">No persisted picks yet.</span>
                )}
              </div>
            </div>

            <div>
              <div className="text-xs uppercase tracking-[0.22em] text-mist/55">Open Exposure</div>
              <div className="mt-3 flex flex-wrap gap-2">
                {exposureBySymbol.length ? (
                  exposureBySymbol.map(([symbol, value]) => (
                    <span
                      key={symbol}
                      className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-sand"
                    >
                      {symbol} {formatCurrency(value)}
                    </span>
                  ))
                ) : (
                  <span className="text-sm text-mist/55">No live exposure.</span>
                )}
              </div>
            </div>
          </div>
        ) : null}
      </div>

      <div className="panel min-w-0 p-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.22em] text-mist/55">AI Telemetry</div>
            <h3 className="mt-3 text-2xl font-semibold text-sand">Decision Layer</h3>
            <p className="mt-2 text-sm leading-6 text-mist/70">
              Provider usage, recent inference status, and accumulated model cost for this strategy desk.
            </p>
          </div>
        </div>
        <div className="mt-4 min-w-0 space-y-3 text-sm text-mist/75">
          <div className="flex items-center justify-between">
            <span>Provider</span>
            <span className="text-sand">{strategy.ai_last_provider || strategy.ai_provider || "--"}</span>
          </div>
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
          <div className="flex items-center justify-between">
            <span>Last call cost</span>
            <span className="text-sand">{formatCurrency(strategy.ai_last_cost_usdt)}</span>
          </div>
          <div className="border-t border-white/10 pt-3 text-xs text-mist/55">
            Detailed AI findings appear in the call log below.
          </div>
          <div className="text-xs text-mist/45">
            Last updated {formatDateTime(strategy.ai_last_decision_at)}
          </div>
        </div>
      </div>
    </section>
  );
}
