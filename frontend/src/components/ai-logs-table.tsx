"use client";

import { Fragment, useState } from "react";
import Link from "next/link";
import { LocalDateTime } from "@/components/local-date-time";
import type { AILogEntry } from "@/lib/types";
import { badgeClassName, buttonClassName } from "@/components/ui";

type Props = {
  logs: AILogEntry[];
  total: number;
  page: number;
  limit: number;
  currentStatus?: string;
  currentStrategyId?: string;
};

function normalizeStatusLabel(status: string) {
  const normalized = status.toLowerCase();
  if (normalized === "signal") return "signal";
  if (normalized === "hold") return "hold";
  if (normalized === "skipped") return "skipped";
  if (normalized === "error") return "error";
  if (normalized === "validated") return "validated";
  if (normalized === "rejected") return "rejected";
  return normalized;
}

function statusTone(status: string): "neutral" | "accent" | "success" | "danger" | "warning" {
  const normalized = normalizeStatusLabel(status);
  if (normalized === "signal" || normalized === "validated") return "success";
  if (normalized === "hold") return "accent";
  if (normalized === "skipped" || normalized === "rejected") return "warning";
  if (normalized === "error") return "danger";
  return "neutral";
}

function StatusBadge({ status, skipReason }: { status: string; skipReason: string | null }) {
  const normalized = normalizeStatusLabel(status);
  const label = skipReason ? `${normalized} (${skipReason})` : normalized;
  return <span className={badgeClassName(statusTone(normalized))}>{label}</span>;
}

function ActionBadge({ action }: { action: string | null }) {
  if (!action) return <span className="text-slate-400">-</span>;
  const colors: Record<string, string> = {
    buy: "text-emerald-700",
    sell: "text-red-700",
    hold: "text-amber-700"
  };
  return <span className={`font-medium uppercase ${colors[action] ?? "text-slate-600"}`}>{action}</span>;
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
    { label: "Signal", value: "signal" },
    { label: "Hold", value: "hold" },
    { label: "Skipped", value: "skipped" },
    { label: "Error", value: "error" }
  ];

  return (
    <section className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">AI call history</h2>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <span className="mr-2 text-xs text-slate-500">Filter:</span>
        {statusFilters.map((filter) => (
          <Link
            key={filter.label}
            href={buildHref({ status: filter.value, strategy_id: currentStrategyId })}
            className={
              currentStatus === filter.value || (!currentStatus && !filter.value)
                ? badgeClassName("accent")
                : badgeClassName("neutral", "hover:bg-slate-200")
            }
          >
            {filter.label}
          </Link>
        ))}
        {currentStrategyId ? (
          <Link
            href={buildHref({ status: currentStatus })}
            className={badgeClassName("danger")}
          >
            Clear strategy filter
          </Link>
        ) : null}
      </div>

      <div className="table-shell overflow-x-auto">
        <table className="data-table">
          <thead>
            <tr>
              <th>Time</th>
              <th>Strategy</th>
              <th>Status</th>
              <th>Action</th>
              <th>Provider / Model</th>
              <th className="text-right">Tokens</th>
              <th className="text-right">Cost</th>
            </tr>
          </thead>
          <tbody>
            {logs.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-slate-500">
                  No AI call logs yet. Logs will appear here once the trading engine makes AI decisions.
                </td>
              </tr>
            ) : null}

            {logs.map((log) => (
              <Fragment key={log.id}>
                <tr
                  onClick={() => setExpandedId(expandedId === log.id ? null : log.id)}
                  className="cursor-pointer"
                >
                  <td className="whitespace-nowrap">
                    <LocalDateTime
                      value={log.created_at}
                      options={{
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                        hour12: false
                      }}
                    />
                  </td>
                  <td>
                    <Link
                      href={buildHref({ strategy_id: log.strategy_id, status: currentStatus })}
                      onClick={(event) => event.stopPropagation()}
                      className="font-medium text-slate-900 transition hover:text-blue-700"
                    >
                      {log.strategy_name}
                    </Link>
                  </td>
                  <td>
                    <StatusBadge status={log.status} skipReason={log.skip_reason} />
                  </td>
                  <td>
                    <ActionBadge action={log.action} />
                  </td>
                  <td>
                    {log.provider ? (
                      <span>
                        {log.provider} <span className="text-slate-400">/ {log.model}</span>
                      </span>
                    ) : (
                      <span className="text-slate-400">-</span>
                    )}
                  </td>
                  <td className="whitespace-nowrap text-right tabular-nums">
                    {log.total_tokens > 0 ? log.total_tokens.toLocaleString() : "-"}
                  </td>
                  <td className="whitespace-nowrap text-right tabular-nums text-blue-700">
                    {log.cost_usdt > 0 ? `$${log.cost_usdt.toFixed(6)}` : "-"}
                  </td>
                </tr>
                {expandedId === log.id ? (
                  <tr className="bg-slate-50">
                    <td colSpan={7} className="px-4 py-4">
                      <div className="grid gap-4 sm:grid-cols-2">
                        <div>
                          <p className="mb-1 text-xs uppercase text-slate-500">Reasoning</p>
                          <p className="whitespace-pre-wrap text-sm text-slate-600">
                            {log.reasoning || log.error || "No details available"}
                          </p>
                        </div>
                        <div className="space-y-2">
                          {log.confidence !== null ? (
                            <div>
                              <span className="text-xs text-slate-500">Confidence: </span>
                              <span className="text-sm text-slate-900">
                                {(log.confidence * 100).toFixed(1)}%
                              </span>
                            </div>
                          ) : null}
                          {log.prompt_tokens > 0 ? (
                            <div>
                              <span className="text-xs text-slate-500">Prompt tokens: </span>
                              <span className="text-sm text-slate-600">
                                {log.prompt_tokens.toLocaleString()}
                              </span>
                              <span className="ml-3 text-xs text-slate-500">Completion: </span>
                              <span className="text-sm text-slate-600">
                                {log.completion_tokens.toLocaleString()}
                              </span>
                            </div>
                          ) : null}
                          <div>
                            <span className="text-xs text-slate-500">Symbol: </span>
                            <span className="text-sm text-slate-600">{log.symbol}</span>
                          </div>
                        </div>
                      </div>
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      {totalPages > 1 ? (
        <div className="flex items-center justify-between">
          <p className="text-xs text-slate-500">
            Showing {(page - 1) * limit + 1}–{Math.min(page * limit, total)} of {total}
          </p>
          <div className="flex gap-2">
            {page > 1 ? (
              <Link
                href={buildHref({ status: currentStatus, strategy_id: currentStrategyId, page: String(page - 1) })}
                className={buttonClassName("secondary", "sm")}
              >
                Prev
              </Link>
            ) : null}
            {page < totalPages ? (
              <Link
                href={buildHref({ status: currentStatus, strategy_id: currentStrategyId, page: String(page + 1) })}
                className={buttonClassName("secondary", "sm")}
              >
                Next
              </Link>
            ) : null}
          </div>
        </div>
      ) : null}
    </section>
  );
}
