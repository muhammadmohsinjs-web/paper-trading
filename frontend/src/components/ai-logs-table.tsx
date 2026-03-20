"use client";

import { useState } from "react";
import Link from "next/link";
import type { AILogEntry } from "@/lib/types";

type Props = {
  logs: AILogEntry[];
  total: number;
  page: number;
  limit: number;
  currentStatus?: string;
  currentStrategyId?: string;
};

function StatusBadge({ status, skipReason }: { status: string; skipReason: string | null }) {
  const colors: Record<string, string> = {
    success: "bg-green-400/15 text-green-400 border-green-400/30",
    skipped: "bg-amber-400/15 text-amber-400 border-amber-400/30",
    error: "bg-red-400/15 text-red-400 border-red-400/30",
  };
  const label = skipReason ? `${status} (${skipReason})` : status;
  return (
    <span className={`inline-block rounded-full border px-2 py-0.5 text-xs ${colors[status] ?? "bg-white/10 text-mist/60 border-white/10"}`}>
      {label}
    </span>
  );
}

function ActionBadge({ action }: { action: string | null }) {
  if (!action) return <span className="text-mist/40">-</span>;
  const colors: Record<string, string> = {
    buy: "text-green-400",
    sell: "text-red-400",
    hold: "text-amber-400",
  };
  return <span className={`font-medium uppercase ${colors[action] ?? "text-mist/60"}`}>{action}</span>;
}

function formatTime(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function buildHref(params: Record<string, string | undefined>) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value) query.set(key, value);
  }
  const qs = query.toString();
  return `/logs${qs ? `?${qs}` : ""}`;
}

export function AILogsTable({ logs, total, page, limit, currentStatus, currentStrategyId }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const totalPages = Math.ceil(total / limit);

  const statusFilters = [
    { label: "All", value: undefined },
    { label: "Success", value: "success" },
    { label: "Skipped", value: "skipped" },
    { label: "Error", value: "error" },
  ];

  return (
    <div className="panel overflow-hidden">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 border-b border-white/10 px-4 py-3">
        <span className="text-xs text-mist/50 mr-2">Filter:</span>
        {statusFilters.map((f) => (
          <Link
            key={f.label}
            href={buildHref({ status: f.value, strategy_id: currentStrategyId })}
            className={`rounded-full border px-3 py-1 text-xs transition ${
              currentStatus === f.value || (!currentStatus && !f.value)
                ? "border-gold/50 bg-gold/10 text-gold"
                : "border-white/10 text-mist/60 hover:border-white/20 hover:text-mist/80"
            }`}
          >
            {f.label}
          </Link>
        ))}
        {currentStrategyId && (
          <Link
            href={buildHref({ status: currentStatus })}
            className="ml-2 rounded-full border border-red-400/30 bg-red-400/10 px-3 py-1 text-xs text-red-400"
          >
            Clear strategy filter
          </Link>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wider text-mist/50">
              <th className="px-4 py-3">Time</th>
              <th className="px-4 py-3">Strategy</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Action</th>
              <th className="px-4 py-3">Provider / Model</th>
              <th className="px-4 py-3 text-right">Tokens</th>
              <th className="px-4 py-3 text-right">Cost</th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-mist/40">
                  No AI call logs yet. Logs will appear here once the trading engine makes AI decisions.
                </td>
              </tr>
            )}
            {logs.map((log) => (
              <>
                <tr
                  key={log.id}
                  onClick={() => setExpandedId(expandedId === log.id ? null : log.id)}
                  className="cursor-pointer border-b border-white/5 transition hover:bg-white/[0.03]"
                >
                  <td className="whitespace-nowrap px-4 py-3 text-mist/70">{formatTime(log.created_at)}</td>
                  <td className="px-4 py-3">
                    <Link
                      href={buildHref({ strategy_id: log.strategy_id, status: currentStatus })}
                      onClick={(e) => e.stopPropagation()}
                      className="text-sand hover:text-gold transition"
                    >
                      {log.strategy_name}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={log.status} skipReason={log.skip_reason} />
                  </td>
                  <td className="px-4 py-3">
                    <ActionBadge action={log.action} />
                  </td>
                  <td className="px-4 py-3 text-mist/60">
                    {log.provider ? (
                      <span>
                        {log.provider} <span className="text-mist/40">/ {log.model}</span>
                      </span>
                    ) : (
                      <span className="text-mist/30">-</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-mist/60">
                    {log.total_tokens > 0 ? log.total_tokens.toLocaleString() : "-"}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-gold">
                    {log.cost_usdt > 0 ? `$${log.cost_usdt.toFixed(6)}` : "-"}
                  </td>
                </tr>
                {expandedId === log.id && (
                  <tr key={`${log.id}-detail`} className="border-b border-white/5 bg-white/[0.02]">
                    <td colSpan={7} className="px-4 py-4">
                      <div className="grid gap-4 sm:grid-cols-2">
                        <div>
                          <p className="mb-1 text-xs uppercase text-mist/40">Reasoning</p>
                          <p className="text-sm text-mist/70 whitespace-pre-wrap">
                            {log.reasoning || log.error || "No details available"}
                          </p>
                        </div>
                        <div className="space-y-2">
                          {log.confidence !== null && (
                            <div>
                              <span className="text-xs text-mist/40">Confidence: </span>
                              <span className="text-sm text-sand">{(log.confidence * 100).toFixed(1)}%</span>
                            </div>
                          )}
                          {log.prompt_tokens > 0 && (
                            <div>
                              <span className="text-xs text-mist/40">Prompt tokens: </span>
                              <span className="text-sm text-mist/60">{log.prompt_tokens.toLocaleString()}</span>
                              <span className="text-xs text-mist/40 ml-3">Completion: </span>
                              <span className="text-sm text-mist/60">{log.completion_tokens.toLocaleString()}</span>
                            </div>
                          )}
                          <div>
                            <span className="text-xs text-mist/40">Symbol: </span>
                            <span className="text-sm text-mist/60">{log.symbol}</span>
                          </div>
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-white/10 px-4 py-3">
          <p className="text-xs text-mist/50">
            Showing {(page - 1) * limit + 1}–{Math.min(page * limit, total)} of {total}
          </p>
          <div className="flex gap-2">
            {page > 1 && (
              <Link
                href={buildHref({ status: currentStatus, strategy_id: currentStrategyId, page: String(page - 1) })}
                className="rounded border border-white/10 px-3 py-1 text-xs text-mist/60 hover:border-white/20"
              >
                Prev
              </Link>
            )}
            {page < totalPages && (
              <Link
                href={buildHref({ status: currentStatus, strategy_id: currentStrategyId, page: String(page + 1) })}
                className="rounded border border-white/10 px-3 py-1 text-xs text-mist/60 hover:border-white/20"
              >
                Next
              </Link>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
