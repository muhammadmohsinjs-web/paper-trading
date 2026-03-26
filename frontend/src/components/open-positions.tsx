import { LocalDateTime } from "@/components/local-date-time";
import { formatCurrency, formatNumber } from "@/lib/format";
import type { Position } from "@/lib/types";

export function OpenPositions({ positions }: { positions: Position[] }) {
  return (
    <div className="panel overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/6 px-5 py-4">
        <div>
          <p className="text-xs uppercase tracking-[0.22em] text-mist/45">Live Holdings</p>
          <h3 className="mt-2 text-xl font-semibold text-sand">Open Positions</h3>
          <p className="text-sm text-mist/55">Current portfolio inventory and unrealized P&amp;L.</p>
        </div>
      </div>

      {positions.length === 0 ? (
        <div className="px-5 py-8 text-sm text-mist/60">No open positions.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-white/[0.03] text-mist/55">
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
                <tr key={position.id} className="border-t border-white/6 transition hover:bg-white/[0.025]">
                  <td className="px-5 py-4 font-medium text-sand">{position.symbol}</td>
                  <td className="px-5 py-4 text-mist/72">{formatNumber(position.quantity, 6)}</td>
                  <td className="px-5 py-4 text-mist/72">{formatCurrency(position.entry_price)}</td>
                  <td className="px-5 py-4 text-mist/72">{formatCurrency(position.current_price)}</td>
                  <td
                    className={`px-5 py-4 ${
                      (position.unrealized_pnl ?? 0) >= 0 ? "text-rise" : "text-fall"
                    }`}
                  >
                    {formatCurrency(position.unrealized_pnl)}
                  </td>
                  <td className="px-5 py-4 text-mist/60">
                    <LocalDateTime value={position.opened_at} />
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
