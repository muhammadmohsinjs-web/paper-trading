import { LocalDateTime } from "@/components/local-date-time";
import { formatCurrency, formatNumber } from "@/lib/format";
import type { Position } from "@/lib/types";
import { CoinIcon } from "@/components/ui";

export function OpenPositions({ positions }: { positions: Position[] }) {
  return (
    <section className="space-y-3">
      <div>
        <h3 className="text-lg font-semibold text-slate-900">Open Positions</h3>
        <p className="text-sm text-slate-600">Current portfolio inventory and unrealized P&amp;L.</p>
      </div>

      {positions.length === 0 ? (
        <div className="border-t border-slate-200 py-6 text-sm text-slate-500">No open positions.</div>
      ) : (
        <div className="table-shell overflow-x-auto">
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Qty</th>
                <th>Entry</th>
                <th>Current</th>
                <th>Unrealized</th>
                <th>Opened</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((position) => (
                <tr key={position.id}>
                  <td className="font-medium text-slate-900">
                    <span className="flex items-center gap-2">
                      <CoinIcon symbol={position.symbol} size={18} />
                      {position.symbol}
                    </span>
                  </td>
                  <td>{formatNumber(position.quantity, 6)}</td>
                  <td>{formatCurrency(position.entry_price)}</td>
                  <td>{formatCurrency(position.current_price)}</td>
                  <td
                    className={(position.unrealized_pnl ?? 0) >= 0 ? "text-emerald-700" : "text-red-700"}
                  >
                    {formatCurrency(position.unrealized_pnl)}
                  </td>
                  <td>
                    <LocalDateTime value={position.opened_at} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
