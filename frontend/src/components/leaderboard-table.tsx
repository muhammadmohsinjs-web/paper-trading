import Link from "next/link";
import { formatCurrency, formatPercent } from "@/lib/format";
import type { LeaderboardEntry } from "@/lib/types";

export function LeaderboardTable({ entries }: { entries: LeaderboardEntry[] }) {
  return (
    <div className="panel overflow-hidden">
      <div className="border-b border-white/10 px-5 py-4">
        <h2 className="text-xl font-semibold text-sand">Leaderboard</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-white/5 text-mist/55">
            <tr>
              <th className="px-5 py-3 font-medium">Rank</th>
              <th className="px-5 py-3 font-medium">Strategy</th>
              <th className="px-5 py-3 font-medium">P&L</th>
              <th className="px-5 py-3 font-medium">Win Rate</th>
              <th className="px-5 py-3 font-medium">Trades</th>
              <th className="px-5 py-3 font-medium">Equity</th>
              <th className="px-5 py-3 font-medium">AI Cost</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.strategy_id} className="border-t border-white/8">
                <td className="px-5 py-4 text-gold">#{entry.rank}</td>
                <td className="px-5 py-4">
                  <Link href={`/strategies/${entry.strategy_id}`} className="font-medium text-sand hover:text-gold">
                    {entry.strategy_name}
                  </Link>
                </td>
                <td className={`px-5 py-4 ${entry.total_pnl >= 0 ? "text-rise" : "text-fall"}`}>
                  {formatCurrency(entry.total_pnl)}
                </td>
                <td className="px-5 py-4">{formatPercent(entry.win_rate)}</td>
                <td className="px-5 py-4">{entry.total_trades}</td>
                <td className="px-5 py-4">{formatCurrency(entry.total_equity)}</td>
                <td className="px-5 py-4">{formatCurrency(entry.ai_total_cost_usdt)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
