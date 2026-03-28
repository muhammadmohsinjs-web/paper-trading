"use client";

import { useState, useEffect, useCallback } from "react";
import {
  getReviewSummary,
  getReviewLedger,
  listReports,
  getReport,
  triggerDailyReport,
} from "@/lib/api";
import { cn, formatPercent } from "@/lib/format";
import { PageHeader, buttonClassName } from "@/components/ui";
import type {
  ReviewSummary,
  LedgerEntry,
  ReportMeta,
  ReportDetail,
  OutcomeBucket,
  RootCause,
} from "@/lib/types";

// ── Colour maps ───────────────────────────────────────────────────────

const BUCKET_META: Record<OutcomeBucket | string, { label: string; color: string }> = {
  good_trade:         { label: "Good trade",          color: "bg-emerald-100 text-emerald-800" },
  bad_trade:          { label: "Bad trade",            color: "bg-red-100 text-red-800" },
  good_skip:          { label: "Good skip",            color: "bg-slate-100 text-slate-700" },
  missed_good_trade:  { label: "Missed opportunity",   color: "bg-amber-100 text-amber-800" },
  open:               { label: "Open",                 color: "bg-blue-100 text-blue-800" },
  insufficient_data:  { label: "Insufficient data",    color: "bg-slate-100 text-slate-500" },
  unclassified:       { label: "Unclassified",         color: "bg-slate-100 text-slate-400" },
};

const CAUSE_META: Record<RootCause | string, { label: string; color: string }> = {
  algorithm_failure:  { label: "Algorithm",   color: "bg-red-100 text-red-800" },
  execution_failure:  { label: "Execution",   color: "bg-orange-100 text-orange-800" },
  strategy_mismatch:  { label: "Mismatch",    color: "bg-amber-100 text-amber-800" },
  market_randomness:  { label: "Randomness",  color: "bg-slate-100 text-slate-600" },
  none:               { label: "None",        color: "bg-slate-50 text-slate-400" },
};

// ── Sub-components ────────────────────────────────────────────────────

function Pill({ value, map }: { value: string | null; map: Record<string, { label: string; color: string }> }) {
  if (!value) return <span className="text-slate-400">—</span>;
  const meta = map[value] ?? { label: value, color: "bg-slate-100 text-slate-600" };
  return (
    <span className={cn("inline-flex items-center rounded px-2 py-0.5 text-xs font-medium", meta.color)}>
      {meta.label}
    </span>
  );
}

function PnlCell({ value }: { value: number | null }) {
  if (value == null) return <span className="text-slate-400">—</span>;
  return (
    <span className={cn("font-mono text-xs", value >= 0 ? "text-emerald-700" : "text-red-600")}>
      {value >= 0 ? "+" : ""}{value.toFixed(2)}%
    </span>
  );
}

function SummaryCards({ summary }: { summary: ReviewSummary }) {
  const buckets = summary.outcome_buckets;
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {[
        { label: "Good trades",       value: buckets.good_trade ?? 0,        color: "text-emerald-700" },
        { label: "Bad trades",        value: buckets.bad_trade ?? 0,         color: "text-red-600" },
        { label: "Missed opps",       value: buckets.missed_good_trade ?? 0, color: "text-amber-700" },
        { label: "Good skips",        value: buckets.good_skip ?? 0,         color: "text-slate-600" },
        { label: "Trades opened",     value: summary.trades_opened,           color: "text-slate-800" },
        { label: "Avg PnL",           value: summary.avg_pnl_pct != null ? `${summary.avg_pnl_pct > 0 ? "+" : ""}${summary.avg_pnl_pct.toFixed(2)}%` : "—", color: summary.avg_pnl_pct != null && summary.avg_pnl_pct >= 0 ? "text-emerald-700" : "text-red-600" },
        { label: "Win rate",          value: summary.win_rate != null ? `${(summary.win_rate * 100).toFixed(0)}%` : "—", color: "text-slate-800" },
        { label: "Symbols evaluated", value: summary.total_symbols_evaluated, color: "text-slate-600" },
      ].map((c) => (
        <div key={c.label} className="rounded-lg border border-slate-200 bg-white p-4">
          <div className="text-xs text-slate-500">{c.label}</div>
          <div className={cn("mt-1 text-2xl font-semibold tabular-nums", c.color)}>{c.value}</div>
        </div>
      ))}
    </div>
  );
}

function RootCauseBar({ causes }: { causes: Record<string, number> }) {
  const total = Object.values(causes).reduce((a, b) => a + b, 0);
  if (total === 0) return <p className="text-sm text-slate-400">No classified causes yet.</p>;
  const order: RootCause[] = ["algorithm_failure", "execution_failure", "strategy_mismatch", "market_randomness"];
  return (
    <div className="space-y-2">
      {order.map((cause) => {
        const count = causes[cause] ?? 0;
        const pct = total > 0 ? (count / total) * 100 : 0;
        const meta = CAUSE_META[cause];
        return (
          <div key={cause} className="flex items-center gap-3">
            <span className={cn("w-28 rounded px-2 py-0.5 text-xs font-medium", meta.color)}>{meta.label}</span>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
              <div className="h-2 rounded-full bg-slate-400" style={{ width: `${pct}%` }} />
            </div>
            <span className="w-12 text-right text-xs text-slate-500">{count} ({pct.toFixed(0)}%)</span>
          </div>
        );
      })}
    </div>
  );
}

function ReportCard({
  report,
  onSelect,
}: {
  report: ReportMeta;
  onSelect: (r: ReportMeta) => void;
}) {
  return (
    <button
      onClick={() => onSelect(report)}
      className="w-full rounded-lg border border-slate-200 bg-white p-4 text-left transition hover:border-slate-400 hover:shadow-sm"
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-800">{report.label}</span>
        <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-500 capitalize">
          {report.subtype}
        </span>
      </div>
      <div className="mt-2 flex gap-4 text-xs text-slate-500">
        <span>✓ {report.good_trades} good</span>
        <span className="text-red-600">✗ {report.bad_trades} bad</span>
        <span className="text-amber-600">⚑ {report.missed_good_trades} missed</span>
        <span className="ml-auto text-slate-400">{(report.confidence_score * 100).toFixed(0)}% confidence</span>
      </div>
    </button>
  );
}

function ReportViewer({ report, onClose }: { report: ReportDetail; onClose: () => void }) {
  // Simple Markdown-to-HTML: headings, tables, bold — good enough for this surface
  const stripFrontmatter = (text: string) => {
    if (!text.startsWith("---")) return text;
    const end = text.indexOf("\n---\n", 4);
    return end === -1 ? text : text.slice(end + 5).trimStart();
  };

  const html = stripFrontmatter(report.content)
    .replace(/^### (.+)$/gm, '<h3 class="mt-5 text-base font-semibold text-slate-800">$1</h3>')
    .replace(/^## (.+)$/gm, '<h2 class="mt-6 text-lg font-bold text-slate-900 border-b pb-1">$1</h2>')
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\| (.+) \|/g, (row) =>
      `<tr>${row.split("|").filter(Boolean).map((cell) =>
        `<td class="border border-slate-200 px-2 py-1 text-xs">${cell.trim()}</td>`
      ).join("")}</tr>`
    )
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc text-sm text-slate-700">$1</li>')
    .replace(/\n\n/g, '</p><p class="mt-3 text-sm text-slate-700">');

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-white">
      <div className="flex items-center justify-between border-b px-6 py-3">
        <span className="font-semibold text-slate-800">{report.label} — {report.type} report</span>
        <button onClick={onClose} className="rounded px-3 py-1 text-sm text-slate-500 hover:bg-slate-100">
          ✕ Close
        </button>
      </div>
      <div
        className="flex-1 overflow-y-auto px-8 py-6 prose prose-slate max-w-none"
        dangerouslySetInnerHTML={{ __html: `<p class="text-sm text-slate-700">${html}</p>` }}
      />
    </div>
  );
}

type Tab = "overview" | "ledger" | "reports";

// ── Main page ─────────────────────────────────────────────────────────

export default function ReviewPage() {
  const [tab, setTab] = useState<Tab>("overview");
  const [days, setDays] = useState(7);

  const [summary, setSummary] = useState<ReviewSummary | null>(null);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [reports, setReports] = useState<ReportMeta[]>([]);
  const [openReport, setOpenReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);

  // Ledger filters
  const [bucketFilter, setBucketFilter] = useState<string>("all");
  const [causeFilter, setCauseFilter] = useState<string>("all");

  const loadOverview = useCallback(async () => {
    setLoading(true);
    try {
      const [s, r] = await Promise.all([getReviewSummary({ days }), listReports()]);
      setSummary(s);
      setReports(r.reports);
    } finally {
      setLoading(false);
    }
  }, [days]);

  const loadLedger = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getReviewLedger({
        outcome_bucket: bucketFilter !== "all" ? bucketFilter : undefined,
        root_cause: causeFilter !== "all" ? causeFilter : undefined,
        limit: 200,
      });
      setLedger(res.items);
    } finally {
      setLoading(false);
    }
  }, [bucketFilter, causeFilter]);

  useEffect(() => {
    if (tab === "overview" || tab === "reports") loadOverview();
  }, [tab, loadOverview]);

  useEffect(() => {
    if (tab === "ledger") loadLedger();
  }, [tab, loadLedger]);

  const handleOpenReport = async (meta: ReportMeta) => {
    const detail = await getReport(meta.subtype, meta.label);
    setOpenReport(detail);
  };

  const handleGenerateDaily = async () => {
    setGenerating(true);
    try {
      await triggerDailyReport();
      setTimeout(loadOverview, 3000); // reload after 3s for the background job
    } finally {
      setGenerating(false);
    }
  };

  const tabs: { id: Tab; label: string }[] = [
    { id: "overview", label: "Overview" },
    { id: "ledger", label: "Decision Ledger" },
    { id: "reports", label: "Reports" },
  ];

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        <PageHeader title="Review System" description="Audit every selection decision and its outcome" />

        {/* Tab bar */}
        <div className="mt-4 flex gap-1 border-b border-slate-200">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "px-4 py-2 text-sm font-medium transition",
                tab === t.id
                  ? "border-b-2 border-slate-900 text-slate-900"
                  : "text-slate-500 hover:text-slate-700"
              )}
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* ── Overview tab ── */}
        {tab === "overview" && (
          <div className="mt-6 space-y-6">
            <div className="flex items-center gap-3">
              <span className="text-sm text-slate-600">Last</span>
              {[7, 14, 30].map((d) => (
                <button
                  key={d}
                  onClick={() => setDays(d)}
                  className={cn(
                    "rounded px-3 py-1 text-sm",
                    days === d ? "bg-slate-900 text-white" : "bg-white border text-slate-600 hover:bg-slate-50"
                  )}
                >
                  {d}d
                </button>
              ))}
              {loading && <span className="text-xs text-slate-400 ml-2">Loading…</span>}
            </div>

            {summary ? (
              <>
                <SummaryCards summary={summary} />
                <div className="rounded-lg border border-slate-200 bg-white p-5">
                  <h3 className="mb-4 text-sm font-semibold text-slate-700">Root Cause Breakdown</h3>
                  <RootCauseBar causes={summary.root_causes} />
                </div>
              </>
            ) : (
              !loading && <p className="text-sm text-slate-400">No review data yet. Data populates after the first trading cycle.</p>
            )}
          </div>
        )}

        {/* ── Ledger tab ── */}
        {tab === "ledger" && (
          <div className="mt-6 space-y-4">
            <div className="flex flex-wrap gap-3">
              <select
                value={bucketFilter}
                onChange={(e) => setBucketFilter(e.target.value)}
                className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm"
              >
                <option value="all">All outcomes</option>
                {Object.entries(BUCKET_META).map(([k, v]) => (
                  <option key={k} value={k}>{v.label}</option>
                ))}
              </select>
              <select
                value={causeFilter}
                onChange={(e) => setCauseFilter(e.target.value)}
                className="rounded border border-slate-300 bg-white px-3 py-1.5 text-sm"
              >
                <option value="all">All root causes</option>
                {Object.entries(CAUSE_META).map(([k, v]) => (
                  <option key={k} value={k}>{v.label}</option>
                ))}
              </select>
              {loading && <span className="text-xs text-slate-400 self-center">Loading…</span>}
            </div>

            <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
              <table className="min-w-full text-xs">
                <thead className="border-b bg-slate-50 text-slate-500">
                  <tr>
                    {["Symbol", "Time", "Setup", "Regime", "Score", "Outcome", "PnL%", "Root Cause", "Hold (h)", "No-exec reason"].map((h) => (
                      <th key={h} className="px-3 py-2 text-left font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {ledger.length === 0 ? (
                    <tr>
                      <td colSpan={10} className="px-4 py-8 text-center text-slate-400">
                        No ledger entries match the current filters.
                      </td>
                    </tr>
                  ) : (
                    ledger.map((e) => (
                      <tr key={e.id} className="hover:bg-slate-50">
                        <td className="px-3 py-2 font-mono font-semibold text-slate-800">{e.symbol}</td>
                        <td className="px-3 py-2 text-slate-500">
                          {e.cycle_ts ? new Date(e.cycle_ts).toLocaleString() : "—"}
                        </td>
                        <td className="px-3 py-2 text-slate-600">{e.setup_type || "—"}</td>
                        <td className="px-3 py-2 text-slate-600">{e.regime_at_decision || "—"}</td>
                        <td className="px-3 py-2 font-mono">{e.composite_score?.toFixed(2) ?? "—"}</td>
                        <td className="px-3 py-2">
                          <Pill value={e.outcome_bucket} map={BUCKET_META} />
                        </td>
                        <td className="px-3 py-2">
                          <PnlCell value={e.realized_pnl_pct} />
                        </td>
                        <td className="px-3 py-2">
                          <Pill value={e.root_cause} map={CAUSE_META} />
                        </td>
                        <td className="px-3 py-2 font-mono">{e.hold_duration_hours?.toFixed(1) ?? "—"}</td>
                        <td className="px-3 py-2 text-slate-500">{e.no_execute_reason || "—"}</td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ── Reports tab ── */}
        {tab === "reports" && (
          <div className="mt-6 space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-sm text-slate-500">{reports.length} report{reports.length !== 1 ? "s" : ""} available</p>
              <button
                onClick={handleGenerateDaily}
                disabled={generating}
                className={cn(buttonClassName("primary", "sm"), "text-sm px-4 py-1.5")}
              >
                {generating ? "Generating…" : "Generate today's report"}
              </button>
            </div>

            {reports.length === 0 ? (
              <p className="text-sm text-slate-400">
                No reports yet. Generate one above or wait for the daily scheduler (01:00 UTC).
              </p>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2">
                {reports.map((r) => (
                  <ReportCard key={`${r.subtype}-${r.label}`} report={r} onSelect={handleOpenReport} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Full-screen report viewer */}
      {openReport && (
        <ReportViewer report={openReport} onClose={() => setOpenReport(null)} />
      )}
    </div>
  );
}
