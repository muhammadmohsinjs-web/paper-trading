import { formatCurrency, formatPercent } from "@/lib/format";
import type { StrategyWithStats, TradeSummary } from "@/lib/types";

type WalletSummaryProps = {
  strategy: StrategyWithStats;
  summary: TradeSummary;
};

function SummaryList({
  items
}: {
  items: Array<{ label: string; value: React.ReactNode; tone?: "default" | "success" | "danger" }>;
}) {
  return (
    <dl className="space-y-3">
      {items.map((item) => (
        <div key={item.label} className="flex items-center justify-between gap-4 text-sm">
          <dt className="text-slate-500">{item.label}</dt>
          <dd
            className={`font-medium ${
              item.tone === "success"
                ? "text-emerald-700"
                : item.tone === "danger"
                  ? "text-red-700"
                  : "text-slate-900"
            }`}
          >
            {item.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export function WalletSummary({ strategy, summary }: WalletSummaryProps) {
  const executionMode = strategy.execution_mode ?? "single_symbol";
  const primarySymbol = strategy.primary_symbol ?? "BTCUSDT";
  const dailyPicks = strategy.daily_picks ?? [];
  const exposureBySymbol = Object.entries(strategy.open_exposure_by_symbol ?? {});
  const riskStatus = (strategy.portfolio_risk_status ?? {}) as {
    exposure_pct?: number;
    drawdown_pct?: number;
    limits?: {
      max_exposure_pct?: number;
      portfolio_drawdown_halt_pct?: number;
    };
  };
  const totalPnlTone =
    strategy.total_pnl > 0 ? "success" : strategy.total_pnl < 0 ? "danger" : "default";
  const unrealizedTone =
    (strategy.unrealized_pnl ?? 0) > 0 ? "success" : (strategy.unrealized_pnl ?? 0) < 0 ? "danger" : "default";

  return (
    <section className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold text-slate-900">Wallet and risk</h3>
        <p className="text-sm text-slate-600">
          {executionMode === "multi_coin_shared_wallet" ? "Shared wallet" : primarySymbol} summary and live limits.
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-2">
        <SummaryList
          items={[
            { label: "Equity", value: formatCurrency(strategy.total_equity) },
            { label: "Initial", value: formatCurrency(strategy.initial_balance_usdt) },
            { label: "Available", value: formatCurrency(strategy.available_usdt) },
            { label: "P&L", value: formatCurrency(strategy.total_pnl), tone: totalPnlTone },
            {
              label: "Unrealized",
              value: strategy.has_open_position ? formatCurrency(strategy.unrealized_pnl) : "—",
              tone: strategy.has_open_position ? unrealizedTone : "default"
            },
            { label: "Win rate", value: formatPercent(summary.win_rate) },
            { label: "Positions", value: strategy.open_positions_count ?? 0 }
          ]}
        />

        <SummaryList
          items={[
            {
              label: "Exposure",
              value:
                riskStatus.exposure_pct != null ? `${riskStatus.exposure_pct.toFixed(2)}%` : "--"
            },
            {
              label: "Drawdown",
              value:
                riskStatus.drawdown_pct != null ? `${riskStatus.drawdown_pct.toFixed(2)}%` : "--"
            },
            {
              label: "Exp. limit",
              value:
                riskStatus.limits?.max_exposure_pct != null
                  ? `${riskStatus.limits.max_exposure_pct}%`
                  : "--"
            },
            {
              label: "DD halt",
              value:
                riskStatus.limits?.portfolio_drawdown_halt_pct != null
                  ? `${riskStatus.limits.portfolio_drawdown_halt_pct}%`
                  : "--"
            }
          ]}
        />
      </div>

      {dailyPicks.length ? (
        <p className="text-sm text-slate-500">
          Picks {dailyPicks.map((pick) => `#${pick.rank} ${pick.symbol}`).join(" · ")}
        </p>
      ) : null}

      {exposureBySymbol.length ? (
        <p className="text-sm text-slate-500">
          Exposure {exposureBySymbol.map(([symbol, value]) => `${symbol} ${formatCurrency(value)}`).join(" · ")}
        </p>
      ) : null}
    </section>
  );
}
