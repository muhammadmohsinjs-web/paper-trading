"use client";

import { Fragment, useState } from "react";
import { LocalDateTime } from "@/components/local-date-time";
import { formatCurrency, formatNumber } from "@/lib/format";
import type { Trade } from "@/lib/types";

const SOURCE_LABELS: Record<string, string> = {
  rule: "Rule",
  ai: "AI",
  hybrid_entry: "Hybrid Entry",
  hybrid_exit: "Hybrid Exit",
  risk: "Risk",
};

const SOURCE_COLORS: Record<string, string> = {
  rule: "bg-blue-400/15 text-blue-400",
  ai: "bg-purple-400/15 text-purple-400",
  hybrid_entry: "bg-gold/15 text-gold",
  hybrid_exit: "bg-amber-400/15 text-amber-400",
  risk: "bg-red-400/15 text-red-400",
};

function IndicatorBadge({ label, value }: { label: string; value: number | undefined }) {
  if (value === undefined || value === null) return null;
  return (
    <span className="inline-flex items-center gap-1 rounded bg-white/5 px-2 py-0.5 text-xs text-mist/70">
      <span className="text-mist/40">{label}</span>
      <span className="font-mono">{formatNumber(value, 4)}</span>
    </span>
  );
}

function TradeDetail({ trade }: { trade: Trade }) {
  const snap = trade.indicator_snapshot;

  return (
    <tr className="border-t border-white/5 bg-white/[0.02]">
      <td colSpan={10} className="px-5 py-4">
        <div className="grid gap-4 md:grid-cols-3">
          {/* Reason / AI Reasoning */}
          {trade.ai_reasoning && (
            <div className="md:col-span-3">
              <span className="text-xs text-mist/40">Reason</span>
              <p className="mt-1 text-sm text-mist/80">{trade.ai_reasoning}</p>
            </div>
          )}

          {/* Indicators */}
          {snap && Object.keys(snap).length > 0 && (
            <div>
              <span className="text-xs text-mist/40">Indicators at Trade</span>
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
          )}

          {/* Composite Score */}
          {(trade.composite_score !== null || trade.composite_confidence !== null) && (
            <div>
              <span className="text-xs text-mist/40">Composite</span>
              <div className="mt-1.5 flex gap-3 text-sm">
                {trade.composite_score !== null && (
                  <span className="text-mist/70">
                    Score: <span className="font-mono text-sand">{formatNumber(trade.composite_score, 4)}</span>
                  </span>
                )}
                {trade.composite_confidence !== null && (
                  <span className="text-mist/70">
                    Confidence: <span className="font-mono text-sand">{formatNumber(trade.composite_confidence, 4)}</span>
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Wallet Balance */}
          {(trade.wallet_balance_before !== null || trade.wallet_balance_after !== null) && (
            <div>
              <span className="text-xs text-mist/40">Wallet</span>
              <div className="mt-1.5 flex gap-3 text-sm">
                {trade.wallet_balance_before !== null && (
                  <span className="text-mist/70">
                    Before: <span className="font-mono">{formatCurrency(trade.wallet_balance_before)}</span>
                  </span>
                )}
                {trade.wallet_balance_after !== null && (
                  <span className="text-mist/70">
                    After: <span className="font-mono">{formatCurrency(trade.wallet_balance_after)}</span>
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      </td>
    </tr>
  );
}

export function TradeLog({ trades }: { trades: Trade[] }) {
  const [expandedId, setExpandedId] = useState<string | null>(null);

  return (
    <div className="panel overflow-hidden">
      <div className="border-b border-white/6 px-5 py-4">
        <p className="text-xs uppercase tracking-[0.22em] text-mist/45">Execution History</p>
        <h3 className="mt-2 text-xl font-semibold text-sand">Trade Log</h3>
      </div>

      {trades.length === 0 ? (
        <div className="px-5 py-8 text-sm text-mist/60">No trades executed yet.</div>
      ) : (
        <div className="max-h-[520px] overflow-auto">
          <table className="min-w-full text-left text-sm">
            <thead className="sticky top-0 bg-[#0f1722] text-mist/55">
              <tr>
                <th className="px-5 py-3 font-medium">Time</th>
                <th className="px-5 py-3 font-medium">Side</th>
                <th className="px-5 py-3 font-medium">Symbol</th>
                <th className="px-5 py-3 font-medium">Source</th>
                <th className="px-5 py-3 font-medium">Strategy</th>
                <th className="px-5 py-3 font-medium">Price</th>
                <th className="px-5 py-3 font-medium">Qty</th>
                <th className="px-5 py-3 font-medium">Cost</th>
                <th className="px-5 py-3 font-medium">Fee</th>
                <th className="px-5 py-3 font-medium">P&L</th>
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
                      className={`border-t border-white/6 ${hasDetails ? "cursor-pointer hover:bg-white/[0.03]" : ""}`}
                      onClick={() => hasDetails && setExpandedId(isExpanded ? null : trade.id)}
                    >
                      <td className="px-5 py-4 text-mist/60">
                        <LocalDateTime value={trade.executed_at} />
                      </td>
                      <td className={`px-5 py-4 font-medium ${trade.side === "BUY" ? "text-rise" : "text-fall"}`}>
                        {trade.side}
                      </td>
                      <td className="px-5 py-4 font-medium text-sand">{trade.symbol}</td>
                      <td className="px-5 py-4">
                        {trade.decision_source ? (
                          <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${SOURCE_COLORS[trade.decision_source] ?? "bg-white/10 text-mist/60"}`}>
                            {SOURCE_LABELS[trade.decision_source] ?? trade.decision_source}
                          </span>
                        ) : (
                          <span className="text-mist/30">--</span>
                        )}
                      </td>
                      <td className="px-5 py-4 text-mist/70">
                        {trade.strategy_name ?? trade.strategy_type ?? "--"}
                      </td>
                      <td className="px-5 py-4">{formatCurrency(trade.price)}</td>
                      <td className="px-5 py-4">{formatNumber(trade.quantity, 6)}</td>
                      <td className="px-5 py-4 font-mono">{formatCurrency(trade.cost_usdt)}</td>
                      <td className="px-5 py-4">{formatCurrency(trade.fee)}</td>
                      <td className={`px-5 py-4 ${(trade.pnl ?? 0) >= 0 ? "text-rise" : "text-fall"}`}>
                        {formatCurrency(trade.pnl)}
                      </td>
                    </tr>
                    {isExpanded && <TradeDetail trade={trade} />}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
