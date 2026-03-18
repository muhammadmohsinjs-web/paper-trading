import { formatCurrency, formatDateTime, formatNumber } from "@/lib/format";
import type { Trade } from "@/lib/types";

export function TradeLog({ trades }: { trades: Trade[] }) {
  return (
    <div className="panel overflow-hidden">
      <div className="border-b border-white/10 px-5 py-4">
        <h3 className="text-lg font-semibold text-sand">Trade Log</h3>
      </div>

      {trades.length === 0 ? (
        <div className="px-5 py-8 text-sm text-mist/60">No trades executed yet.</div>
      ) : (
        <div className="max-h-[420px] overflow-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="sticky top-0 bg-panel text-mist/55">
              <tr>
                <th className="px-5 py-3 font-medium">Time</th>
                <th className="px-5 py-3 font-medium">Side</th>
                <th className="px-5 py-3 font-medium">Price</th>
                <th className="px-5 py-3 font-medium">Qty</th>
                <th className="px-5 py-3 font-medium">Fee</th>
                <th className="px-5 py-3 font-medium">P&L</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => (
                <tr key={trade.id} className="border-t border-white/8">
                  <td className="px-5 py-4 text-mist/60">{formatDateTime(trade.executed_at)}</td>
                  <td className={`px-5 py-4 font-medium ${trade.side === "BUY" ? "text-rise" : "text-fall"}`}>
                    {trade.side}
                  </td>
                  <td className="px-5 py-4">{formatCurrency(trade.price)}</td>
                  <td className="px-5 py-4">{formatNumber(trade.quantity, 6)}</td>
                  <td className="px-5 py-4">{formatCurrency(trade.fee)}</td>
                  <td className={`px-5 py-4 ${(trade.pnl ?? 0) >= 0 ? "text-rise" : "text-fall"}`}>
                    {formatCurrency(trade.pnl)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
