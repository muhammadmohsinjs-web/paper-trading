import Link from "next/link";
import { formatCurrency, formatPercent } from "@/lib/format";
import type { LeaderboardEntry } from "@/lib/types";
import { buttonClassName } from "@/components/ui";

export function LeaderboardTable({ entries }: { entries: LeaderboardEntry[] }) {
  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">Leaderboard</h2>
      </div>

      <div className="table-shell overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Strategy</th>
              <th>Realized P&amp;L</th>
              <th>Unrealized P&amp;L</th>
              <th>Win Rate</th>
              <th>Trades</th>
              <th>Equity</th>
              <th>AI Cost</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.strategy_id}>
                <td className="font-medium text-slate-500">#{entry.rank}</td>
                <td>
                  <Link
                    href={`/strategies/${entry.strategy_id}`}
                    className="font-medium text-slate-900 hover:text-blue-700"
                  >
                    {entry.strategy_name}
                  </Link>
                </td>
                <td className={entry.total_pnl >= 0 ? "text-emerald-700" : "text-red-700"}>
                  {formatCurrency(entry.total_pnl)}
                </td>
                <td>
                  {entry.has_open_position ? (
                    <span className={entry.unrealized_pnl >= 0 ? "text-emerald-700" : "text-red-700"}>
                      {formatCurrency(entry.unrealized_pnl)}
                    </span>
                  ) : (
                    <span className="text-slate-400">&mdash;</span>
                  )}
                </td>
                <td>{formatPercent(entry.win_rate)}</td>
                <td>{entry.total_trades}</td>
                <td className="font-medium text-slate-900">{formatCurrency(entry.total_equity)}</td>
                <td>{formatCurrency(entry.ai_total_cost_usdt)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div>
        <Link href="/" className={buttonClassName("secondary", "sm")}>
          Back to overview
        </Link>
      </div>
    </section>
  );
}
