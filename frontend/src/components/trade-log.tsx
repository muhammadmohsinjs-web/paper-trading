"use client";

import { Fragment, useState } from "react";
import { LocalDateTime } from "@/components/local-date-time";
import { formatCurrency, formatNumber } from "@/lib/format";
import type { Trade } from "@/lib/types";
import { badgeClassName } from "@/components/ui";

const SOURCE_LABELS: Record<string, string> = {
  rule: "Rule",
  ai: "AI",
  hybrid_entry: "Hybrid Entry",
  hybrid_exit: "Hybrid Exit",
  risk: "Risk"
};

function sourceTone(source: string | null): "neutral" | "accent" | "warning" | "danger" {
  if (source === "ai") return "accent";
  if (source === "risk") return "danger";
  if (source === "hybrid_exit") return "warning";
  return "neutral";
}

function IndicatorBadge({ label, value }: { label: string; value: number | undefined }) {
  if (value === undefined || value === null) return null;
  return (
    <span className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
      <span className="text-slate-500">{label}</span>
      <span className="font-mono">{formatNumber(value, 4)}</span>
    </span>
  );
}

function TradeDetail({ trade }: { trade: Trade }) {
  const snap = trade.indicator_snapshot;

  return (
    <tr className="border-t border-slate-200 bg-slate-50">
      <td colSpan={10} className="px-5 py-4">
        <div className="grid gap-4 md:grid-cols-3">
          {trade.ai_reasoning ? (
            <div className="md:col-span-3">
              <span className="text-xs text-slate-500">Reason</span>
              <p className="mt-1 text-sm text-slate-700">{trade.ai_reasoning}</p>
            </div>
          ) : null}

          {snap && Object.keys(snap).length > 0 ? (
            <div>
              <span className="text-xs text-slate-500">Indicators at trade</span>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                <IndicatorBadge label="RSI" value={snap.rsi} />
                <IndicatorBadge label="ATR" value={snap.atr} />
                <IndicatorBadge label="Vol" value={snap.volume_ratio} />
                <IndicatorBadge label="MACD" value={snap.macd_line} />
                <IndicatorBadge label="Sig" value={snap.macd_signal} />
                <IndicatorBadge label="Hist" value={snap.macd_histogram} />
                <IndicatorBadge label="SMA-S" value={snap.sma_short} />
                <IndicatorBadge label="SMA-L" value={snap.sma_long} />
                <IndicatorBadge label="BB-U" value={snap.bb_upper} />
                <IndicatorBadge label="BB-M" value={snap.bb_middle} />
                <IndicatorBadge label="BB-L" value={snap.bb_lower} />
              </div>
            </div>
          ) : null}

          {trade.composite_score !== null || trade.composite_confidence !== null ? (
            <div>
              <span className="text-xs text-slate-500">Composite</span>
              <div className="mt-1.5 flex gap-3 text-sm">
                {trade.composite_score !== null ? (
                  <span className="text-slate-600">
                    Score: <span className="font-mono text-slate-900">{formatNumber(trade.composite_score, 4)}</span>
                  </span>
                ) : null}
                {trade.composite_confidence !== null ? (
                  <span className="text-slate-600">
                    Confidence:{" "}
                    <span className="font-mono text-slate-900">
                      {formatNumber(trade.composite_confidence, 4)}
                    </span>
                  </span>
                ) : null}
              </div>
            </div>
          ) : null}

          {trade.wallet_balance_before !== null || trade.wallet_balance_after !== null ? (
            <div>
              <span className="text-xs text-slate-500">Wallet</span>
              <div className="mt-1.5 flex gap-3 text-sm">
                {trade.wallet_balance_before !== null ? (
                  <span className="text-slate-600">
                    Before: <span className="font-mono">{formatCurrency(trade.wallet_balance_before)}</span>
                  </span>
                ) : null}
                {trade.wallet_balance_after !== null ? (
                  <span className="text-slate-600">
                    After: <span className="font-mono">{formatCurrency(trade.wallet_balance_after)}</span>
                  </span>
                ) : null}
              </div>
            </div>
          ) : null}
        </div>
      </td>
    </tr>
  );
}

export function TradeLog({ trades }: { trades: Trade[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <section className="space-y-3">
      <div>
        <h3 className="text-lg font-semibold text-slate-900">Trade Log</h3>
        <p className="text-sm text-slate-600">Executed orders, sources, and detail snapshots.</p>
      </div>

      {trades.length === 0 ? (
        <div className="border-t border-slate-200 py-6 text-sm text-slate-500">No trades executed yet.</div>
      ) : (
        <div className="table-shell max-h-[520px] overflow-auto">
          <table className="data-table">
            <thead className="sticky top-0">
              <tr>
                <th>Time</th>
                <th>Side</th>
                <th>Symbol</th>
                <th>Source</th>
                <th>Strategy</th>
                <th>Price</th>
                <th>Qty</th>
                <th>Cost</th>
                <th>Fee</th>
                <th>P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {trades.map((trade) => {
                const isExpanded = expandedId === trade.id;
                const hasDetails =
                  trade.indicator_snapshot ||
                  trade.ai_reasoning ||
                  trade.composite_score !== null ||
                  trade.wallet_balance_before !== null;

                return (
                  <Fragment key={trade.id}>
                    <tr
                      className={hasDetails ? "cursor-pointer" : ""}
                      onClick={() => hasDetails && setExpandedId(isExpanded ? null : trade.id)}
                    >
                      <td>
                        <LocalDateTime value={trade.executed_at} />
                      </td>
                      <td className={`font-medium ${trade.side === "BUY" ? "text-emerald-700" : "text-red-700"}`}>
                        {trade.side}
                      </td>
                      <td className="font-medium text-slate-900">{trade.symbol}</td>
                      <td>
                        {trade.decision_source ? (
                          <span className={badgeClassName(sourceTone(trade.decision_source))}>
                            {SOURCE_LABELS[trade.decision_source] ?? trade.decision_source}
                          </span>
                        ) : (
                          <span className="text-slate-400">--</span>
                        )}
                      </td>
                      <td>{trade.strategy_name ?? trade.strategy_type ?? "--"}</td>
                      <td>{formatCurrency(trade.price)}</td>
                      <td>{formatNumber(trade.quantity, 6)}</td>
                      <td className="font-mono">{formatCurrency(trade.cost_usdt)}</td>
                      <td>{formatCurrency(trade.fee)}</td>
                      <td className={(trade.pnl ?? 0) >= 0 ? "text-emerald-700" : "text-red-700"}>
                        {formatCurrency(trade.pnl)}
                      </td>
                    </tr>
                    {isExpanded ? <TradeDetail trade={trade} /> : null}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
