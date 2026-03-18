import Link from "next/link";
import { PriceChart } from "@/components/price-chart";
import { formatCurrency, formatPercent } from "@/lib/format";
import type { EquityPoint, StrategyWithStats } from "@/lib/types";

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

      <div className="panel overflow-hidden">
        <div className="border-b border-white/10 px-5 py-4">
          <h2 className="text-xl font-semibold text-sand">Metrics Table</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-white/5 text-mist/55">
              <tr>
                <th className="px-5 py-3 font-medium">Metric</th>
                <th className="px-5 py-3 font-medium">{left.name}</th>
                <th className="px-5 py-3 font-medium">{right.name}</th>
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
                <tr key={label} className="border-t border-white/8">
                  <td className="px-5 py-4 text-mist/60">{label}</td>
                  <td className="px-5 py-4 text-sand">{leftValue}</td>
                  <td className="px-5 py-4 text-sand">{rightValue}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="flex gap-3">
        <Link href={`/strategies/${left.id}`} className="rounded-full border border-white/10 px-4 py-2 text-sm text-mist hover:border-gold/40 hover:text-gold">
          Open {left.name}
        </Link>
        <Link href={`/strategies/${right.id}`} className="rounded-full border border-white/10 px-4 py-2 text-sm text-mist hover:border-gold/40 hover:text-gold">
          Open {right.name}
        </Link>
      </div>
    </div>
  );
}
