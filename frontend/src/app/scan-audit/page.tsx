"use client";

import { useState, useCallback, useMemo } from "react";
import { runManualScan } from "@/lib/api";
import { cn, formatCurrency, formatNumber, formatPercent } from "@/lib/format";
import type {
  ManualScanResponse,
  ScanAuditRow,
  CandidateEvaluation,
  FunnelStats,
} from "@/lib/types";
import { PageHeader, MetricStrip, CoinIcon, buttonClassName } from "@/components/ui";

type FilterLayer =
  | "all"
  | "universe_rejected"
  | "no_data"
  | "tradability_rejected"
  | "no_setup"
  | "low_liquidity"
  | "qualified";

const LAYER_META: Record<FilterLayer, { label: string; tone: string }> = {
  all: { label: "All symbols", tone: "text-slate-700 bg-slate-100" },
  universe_rejected: {
    label: "Rejected at tradability (universe)",
    tone: "text-red-700 bg-red-50",
  },
  no_data: { label: "No data", tone: "text-slate-600 bg-slate-100" },
  tradability_rejected: {
    label: "Tradability rejected (scan)",
    tone: "text-red-700 bg-red-50",
  },
  no_setup: { label: "No setup detected", tone: "text-amber-700 bg-amber-50" },
  low_liquidity: {
    label: "Low liquidity",
    tone: "text-orange-700 bg-orange-50",
  },
  qualified: { label: "Qualified", tone: "text-emerald-700 bg-emerald-50" },
};

function ReasonBadge({ code }: { code: string }) {
  return (
    <span className="inline-block rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-slate-600">
      {code.replace(/_/g, " ")}
    </span>
  );
}

function FiltrationFunnel({ funnel }: { funnel: FunnelStats }) {
  const stages = [
    { label: "USDT pairs discovered", count: funnel.total_usdt_pairs },
    { label: "After hard filters", count: funnel.after_hard_filters },
    { label: "After tradability", count: funnel.after_tradability },
    { label: "Active universe", count: funnel.active_universe, accent: true },
    { label: "With sufficient data", count: funnel.with_data },
    { label: "Setup detected", count: funnel.after_setup_detection },
    {
      label: "Passed liquidity floor",
      count: funnel.after_liquidity_floor,
    },
    { label: "Final ranked", count: funnel.final_ranked, success: true },
  ];

  const maxCount = stages[0].count || 1;

  return (
    <div className="table-shell">
      <div className="border-b border-slate-200 bg-slate-50 px-4 py-2 text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">
        Filtration funnel
      </div>
      <div className="divide-y divide-slate-100">
        {stages.map((stage) => {
          const pct = Math.max((stage.count / maxCount) * 100, 2);
          return (
            <div
              key={stage.label}
              className="flex items-center gap-4 px-4 py-2"
            >
              <span className="w-40 shrink-0 text-xs text-slate-600">
                {stage.label}
              </span>
              <div className="flex-1">
                <div
                  className={cn(
                    "h-3.5 rounded",
                    stage.success
                      ? "bg-emerald-500"
                      : stage.accent
                        ? "bg-blue-500"
                        : "bg-slate-300"
                  )}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <span className="w-12 text-right text-sm font-medium tabular-nums text-slate-900">
                {formatNumber(stage.count, 0)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function UniverseRejectedTable({
  candidates,
}: {
  candidates: CandidateEvaluation[];
}) {
  const rejected = candidates.filter((c) => !c.tradability_passed);
  if (rejected.length === 0)
    return (
      <p className="py-4 text-sm text-slate-500">
        No candidates rejected at universe tradability stage.
      </p>
    );

  return (
    <div className="table-shell">
      <div className="grid grid-cols-[6rem_4.5rem_6rem_5rem_5rem_1fr] gap-3 border-b border-slate-200 bg-slate-50 px-4 py-2 text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">
        <span>Symbol</span>
        <span className="text-right">Price</span>
        <span className="text-right">24h Vol</span>
        <span className="text-right">Change</span>
        <span className="text-right">Quality</span>
        <span>Rejection reason</span>
      </div>
      {rejected.map((c) => (
        <div
          key={c.symbol}
          className="grid grid-cols-[6rem_4.5rem_6rem_5rem_5rem_1fr] items-center gap-3 border-b border-slate-100 px-4 py-2.5 text-sm last:border-b-0"
        >
          <span className="flex items-center gap-2 font-medium text-slate-900">
            <CoinIcon symbol={c.symbol} size={18} />
            {c.symbol.replace("USDT", "")}
          </span>
          <span className="text-right tabular-nums text-slate-600">
            ${formatNumber(c.price, c.price < 1 ? 4 : 2)}
          </span>
          <span className="text-right tabular-nums text-slate-600">
            {formatCurrency(c.volume_24h_usdt, true)}
          </span>
          <span
            className={cn(
              "text-right tabular-nums",
              c.price_change_pct_24h >= 0
                ? "text-emerald-700"
                : "text-red-700"
            )}
          >
            {formatPercent(c.price_change_pct_24h / 100)}
          </span>
          <span className="text-right tabular-nums text-slate-600">
            {formatNumber(c.market_quality_score * 100, 0)}
          </span>
          <div className="flex flex-wrap gap-1">
            {c.reason_codes.map((code) => (
              <ReasonBadge key={code} code={code} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function ScanAuditTable({
  rows,
  filter,
}: {
  rows: ScanAuditRow[];
  filter: FilterLayer;
}) {
  const filtered = useMemo(() => {
    if (filter === "all") return rows;
    if (filter === "no_data")
      return rows.filter((r) => r.reason_code === "MARKET_DATA_INSUFFICIENT");
    if (filter === "tradability_rejected")
      return rows.filter(
        (r) =>
          r.status === "rejected" &&
          r.reason_code !== "MARKET_DATA_INSUFFICIENT" &&
          r.reason_code !== "NO_QUALIFYING_SETUP" &&
          r.reason_code !== "LIQUIDITY_TOO_LOW"
      );
    if (filter === "no_setup")
      return rows.filter((r) => r.reason_code === "NO_QUALIFYING_SETUP");
    if (filter === "low_liquidity")
      return rows.filter((r) => r.reason_code === "LIQUIDITY_TOO_LOW");
    if (filter === "qualified")
      return rows.filter((r) => r.status === "qualified");
    return rows;
  }, [rows, filter]);

  if (filtered.length === 0)
    return (
      <p className="py-4 text-sm text-slate-500">
        No symbols in this category.
      </p>
    );

  return (
    <div className="table-shell">
      <div className="grid grid-cols-[6rem_5rem_6rem_1fr_5rem] gap-3 border-b border-slate-200 bg-slate-50 px-4 py-2 text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">
        <span>Symbol</span>
        <span>Status</span>
        <span>Setup</span>
        <span>Reason</span>
        <span className="text-right">Score</span>
      </div>
      {filtered.map((row, idx) => (
        <div
          key={`${row.symbol}-${idx}`}
          className="grid grid-cols-[6rem_5rem_6rem_1fr_5rem] items-center gap-3 border-b border-slate-100 px-4 py-2.5 text-sm last:border-b-0"
        >
          <span className="flex items-center gap-2 font-medium text-slate-900">
            <CoinIcon symbol={row.symbol} size={18} />
            {row.symbol.replace("USDT", "")}
          </span>
          <span>
            <span
              className={cn(
                "inline-block rounded px-1.5 py-0.5 text-[10px] font-medium uppercase",
                row.status === "qualified"
                  ? "bg-emerald-50 text-emerald-700"
                  : row.status === "skipped"
                    ? "bg-slate-100 text-slate-600"
                    : "bg-red-50 text-red-700"
              )}
            >
              {row.status}
            </span>
          </span>
          <span className="text-xs text-slate-600">
            {row.setup_type?.replace(/_/g, " ") ?? "-"}
          </span>
          <div className="min-w-0">
            {row.reason_code && <ReasonBadge code={row.reason_code} />}
            <p className="mt-0.5 truncate text-xs text-slate-500">
              {row.reason_text}
            </p>
          </div>
          <span className="text-right tabular-nums text-slate-600">
            {row.score > 0 ? formatNumber(row.score * 100, 0) : "-"}
          </span>
        </div>
      ))}
    </div>
  );
}

export default function ScanAuditPage() {
  const [scanResult, setScanResult] = useState<ManualScanResponse | null>(null);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [interval, setIntervalValue] = useState("1h");
  const [activeFilter, setActiveFilter] = useState<FilterLayer>("all");

  const handleScan = useCallback(async () => {
    setScanning(true);
    setError(null);
    try {
      const result = await runManualScan(interval, 15);
      setScanResult(result);
      setActiveFilter("all");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setScanning(false);
    }
  }, [interval]);

  const auditRows = scanResult?.audit_rows ?? [];
  const candidates = scanResult?.candidate_evaluations ?? [];

  const layerCounts = useMemo(() => {
    const noData = auditRows.filter(
      (r) => r.reason_code === "MARKET_DATA_INSUFFICIENT"
    ).length;
    const tradRej = auditRows.filter(
      (r) =>
        r.status === "rejected" &&
        r.reason_code !== "MARKET_DATA_INSUFFICIENT" &&
        r.reason_code !== "NO_QUALIFYING_SETUP" &&
        r.reason_code !== "LIQUIDITY_TOO_LOW"
    ).length;
    const noSetup = auditRows.filter(
      (r) => r.reason_code === "NO_QUALIFYING_SETUP"
    ).length;
    const lowLiq = auditRows.filter(
      (r) => r.reason_code === "LIQUIDITY_TOO_LOW"
    ).length;
    const qualified = auditRows.filter((r) => r.status === "qualified").length;
    const univRej = candidates.filter((c) => !c.tradability_passed).length;

    return {
      all: auditRows.length,
      universe_rejected: univRej,
      no_data: noData,
      tradability_rejected: tradRej,
      no_setup: noSetup,
      low_liquidity: lowLiq,
      qualified,
    };
  }, [auditRows, candidates]);

  const filters: FilterLayer[] = [
    "all",
    "universe_rejected",
    "no_data",
    "tradability_rejected",
    "no_setup",
    "low_liquidity",
    "qualified",
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Scan audit"
        description="Detailed breakdown of every coin at each filtration layer with rejection reasons."
        actions={
          <div className="flex items-center gap-3">
            <select
              value={interval}
              onChange={(e) => setIntervalValue(e.target.value)}
              className="rounded-[10px] border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 outline-none focus:border-blue-300"
            >
              <option value="5m">5m</option>
              <option value="1h">1h</option>
              <option value="4h">4h</option>
            </select>
            <button
              onClick={handleScan}
              disabled={scanning}
              className={buttonClassName("primary", "md")}
            >
              {scanning ? "Scanning..." : "Run scan"}
            </button>
          </div>
        }
      />

      {error ? <p className="text-sm text-red-700">{error}</p> : null}

      {scanResult ? (
        <>
          {scanResult.funnel ? (
            <FiltrationFunnel funnel={scanResult.funnel} />
          ) : null}

          <MetricStrip
            items={[
              {
                label: "Universe scanned",
                value: formatNumber(scanResult.universe_size, 0),
              },
              {
                label: "Universe tradability rejected",
                value: formatNumber(layerCounts.universe_rejected, 0),
                tone: "danger",
              },
              {
                label: "No data",
                value: formatNumber(layerCounts.no_data, 0),
              },
              {
                label: "Tradability rejected",
                value: formatNumber(layerCounts.tradability_rejected, 0),
                tone: "danger",
              },
              {
                label: "No setup",
                value: formatNumber(layerCounts.no_setup, 0),
                tone: "warning",
              },
              {
                label: "Low liquidity",
                value: formatNumber(layerCounts.low_liquidity, 0),
                tone: "warning",
              },
              {
                label: "Qualified",
                value: formatNumber(layerCounts.qualified, 0),
                tone: "success",
              },
            ]}
          />

          {/* Filter tabs */}
          <div className="flex flex-wrap gap-2">
            {filters.map((f) => {
              const meta = LAYER_META[f];
              const count = layerCounts[f];
              return (
                <button
                  key={f}
                  onClick={() => setActiveFilter(f)}
                  className={cn(
                    "rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                    activeFilter === f
                      ? meta.tone
                      : "bg-white text-slate-500 hover:bg-slate-50"
                  )}
                >
                  {meta.label} ({count})
                </button>
              );
            })}
          </div>

          {/* Show appropriate table based on filter */}
          {activeFilter === "universe_rejected" ? (
            <UniverseRejectedTable candidates={candidates} />
          ) : (
            <ScanAuditTable rows={auditRows} filter={activeFilter} />
          )}

          <p className="text-xs text-slate-500">
            Scanned at{" "}
            {new Date(scanResult.scanned_at).toLocaleTimeString()} on{" "}
            {interval} timeframe.
          </p>
        </>
      ) : (
        <div className="border-t border-slate-200 py-8 text-center">
          <p className="text-sm text-slate-500">
            Press{" "}
            <span className="font-medium text-blue-700">Run scan</span> to
            see the full filtration audit.
          </p>
        </div>
      )}
    </div>
  );
}
