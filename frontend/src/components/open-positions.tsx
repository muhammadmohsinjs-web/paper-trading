import { formatCurrency, formatDateTime, formatNumber } from "@/lib/format";
import type { Position } from "@/lib/types";

export function OpenPositions({ positions }: { positions: Position[] }) {
  return (
    <div className="panel overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/10 px-5 py-4">
        <div>
          <h3 className="text-lg font-semibold text-sand">Open Positions</h3>
          <p className="text-sm text-mist/55">Current live holdings and unrealized P&L.</p>
        </div>
      </div>

      {positions.length === 0 ? (
        <div className="px-5 py-8 text-sm text-mist/60">No open positions.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-white/5 text-mist/55">
              <tr>
                <th className="px-5 py-3 font-medium">Symbol</th>
                <th className="px-5 py-3 font-medium">Qty</th>
                <th className="px-5 py-3 font-medium">Entry</th>
                <th className="px-5 py-3 font-medium">Current</th>
                <th className="px-5 py-3 font-medium">Unrealized</th>
                <th className="px-5 py-3 font-medium">Opened</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((position) => (
                <tr key={position.id} className="border-t border-white/8">
                  <td className="px-5 py-4 font-medium text-sand">{position.symbol}</td>
                  <td className="px-5 py-4">{formatNumber(position.quantity, 6)}</td>
                  <td className="px-5 py-4">{formatCurrency(position.entry_price)}</td>
                  <td className="px-5 py-4">{formatCurrency(position.current_price)}</td>
                  <td
                    className={`px-5 py-4 ${
                      (position.unrealized_pnl ?? 0) >= 0 ? "text-rise" : "text-fall"
                    }`}
                  >
                    {formatCurrency(position.unrealized_pnl)}
                  </td>
                  <td className="px-5 py-4 text-mist/60">{formatDateTime(position.opened_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
