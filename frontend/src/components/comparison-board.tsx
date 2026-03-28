import Link from "next/link";
import { PriceChart } from "@/components/price-chart";
import { formatCurrency, formatPercent } from "@/lib/format";
import type { EquityPoint, StrategyWithStats } from "@/lib/types";
import { buttonClassName } from "@/components/ui";

type ComparisonBoardProps = {
  left: StrategyWithStats;
  right: StrategyWithStats;
  leftEquity: EquityPoint[];
  rightEquity: EquityPoint[];
};

export function ComparisonBoard({ left, right, leftEquity, rightEquity }: ComparisonBoardProps) {
  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <PriceChart title={`${left.name} Equity`} candles={[]} equity={leftEquity} mode="equity" />
        <PriceChart title={`${right.name} Equity`} candles={[]} equity={rightEquity} mode="equity" />
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-slate-900">Metrics table</h2>
        <div className="table-shell overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th>{left.name}</th>
                <th>{right.name}</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["Equity", formatCurrency(left.total_equity), formatCurrency(right.total_equity)],
                ["P&L", formatCurrency(left.total_pnl), formatCurrency(right.total_pnl)],
                ["Win Rate", formatPercent(left.win_rate), formatPercent(right.win_rate)],
                ["Trades", String(left.total_trades), String(right.total_trades)],
                ["AI Calls", String(left.ai_total_calls), String(right.ai_total_calls)]
              ].map(([label, leftValue, rightValue]) => (
                <tr key={label}>
                  <td>{label}</td>
                  <td className="font-medium text-slate-900">{leftValue}</td>
                  <td className="font-medium text-slate-900">{rightValue}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className="flex gap-3">
        <Link href={`/strategies/${left.id}`} className={buttonClassName("secondary", "sm")}>
          Open {left.name}
        </Link>
        <Link href={`/strategies/${right.id}`} className={buttonClassName("secondary", "sm")}>
          Open {right.name}
        </Link>
      </div>
    </div>
  );
}
