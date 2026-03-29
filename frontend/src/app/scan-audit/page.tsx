"use client";

import { useState, useCallback, useEffect, useMemo } from "react";
import { refreshScannerLiveData, runManualScan } from "@/lib/api";
import { cn, formatCurrency, formatNumber, formatPercent } from "@/lib/format";
import type {
  ManualScanResponse,
  ScanAuditRow,
  CandidateEvaluation,
  FunnelStats,
  ScannerRefreshResponse,
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

type SortDirection = "asc" | "desc";
type AuditSortKey =
  | "symbol"
  | "layer"
  | "status"
  | "liquidity_archetype"
  | "setup_type"
  | "price"
  | "volume_1h_usdt"
  | "threshold_volume_1h_usdt"
  | "volume_24h_usdt"
  | "threshold_volume_24h_usdt"
  | "price_change_pct_24h"
  | "market_quality_score"
  | "net_quality_score"
  | "reason"
  | "score";

type UnifiedAuditRow = ScanAuditRow & {
  layer: Exclude<FilterLayer, "all">;
  liquidity_archetype: string | null;
  price: number | null;
  volume_1h_usdt: number | null;
  threshold_volume_1h_usdt: number | null;
  volume_24h_usdt: number | null;
  threshold_volume_24h_usdt: number | null;
  price_change_pct_24h: number | null;
  market_quality_score: number | null;
  net_quality_score: number | null;
};

function compareText(a: string | null | undefined, b: string | null | undefined) {
  return (a ?? "").localeCompare(b ?? "");
}

function sortableNumber(
  value: number | null | undefined,
  direction: SortDirection
) {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return direction === "asc" ? Number.POSITIVE_INFINITY : Number.NEGATIVE_INFINITY;
  }

  return value;
}

function toggleSort<T extends string>(
  current: { key: T; direction: SortDirection },
  nextKey: T,
  initialDirection: SortDirection
) {
  if (current.key === nextKey) {
    return {
      key: nextKey,
      direction: current.direction === "asc" ? "desc" : "asc",
    };
  }
  return { key: nextKey, direction: initialDirection };
}

function auditSortDirection(key: AuditSortKey): SortDirection {
  switch (key) {
    case "symbol":
    case "layer":
    case "liquidity_archetype":
    case "setup_type":
    case "reason":
      return "asc";
    default:
      return "desc";
  }
}

function classifyAuditLayer(row: ScanAuditRow): Exclude<FilterLayer, "all" | "universe_rejected"> {
  if (row.reason_code === "MARKET_DATA_INSUFFICIENT") return "no_data";
  if (row.reason_code === "NO_QUALIFYING_SETUP") return "no_setup";
  if (row.reason_code === "LIQUIDITY_TOO_LOW") return "low_liquidity";
  if (row.status === "qualified") return "qualified";
  return "tradability_rejected";
}

function SortHeader<T extends string>({
  label,
  sortKey,
  activeSort,
  onSort,
  align = "left",
}: {
  label: string;
  sortKey: T;
  activeSort: { key: T; direction: SortDirection };
  onSort: (key: T) => void;
  align?: "left" | "right";
}) {
  const isActive = activeSort.key === sortKey;

  return (
    <button
      type="button"
      onClick={() => onSort(sortKey)}
      className={cn(
        "flex w-full items-center gap-1 text-left transition-colors hover:text-slate-700",
        align === "right" ? "justify-end" : "justify-start"
      )}
      aria-label={`Sort by ${label.toLowerCase()}${isActive ? ` (${activeSort.direction})` : ""}`}
    >
      <span>{label}</span>
      {isActive ? (
        <span className="text-[10px] text-slate-400">
          [{activeSort.direction}]
        </span>
      ) : null}
    </button>
  );
}

function ReasonBadge({ code }: { code: string }) {
  return (
    <span className="inline-block rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-slate-600">
      {code.replace(/_/g, " ")}
    </span>
  );
}

function LiquidityArchetypeBadge({ archetype }: { archetype: string | null }) {
  if (!archetype) {
    return <span className="text-slate-400">-</span>;
  }

  const tone =
    archetype === "major"
      ? "bg-blue-50 text-blue-700"
      : archetype === "mid"
        ? "bg-emerald-50 text-emerald-700"
        : archetype === "meme"
          ? "bg-amber-50 text-amber-700"
          : "bg-slate-100 text-slate-600";

  return (
    <span className={cn("inline-block rounded px-1.5 py-0.5 text-[10px] font-medium uppercase", tone)}>
      {archetype}
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

function ScanAuditTable({
  rows,
  filter,
}: {
  rows: UnifiedAuditRow[];
  filter: FilterLayer;
}) {
  const defaultSort = useMemo<{ key: AuditSortKey; direction: SortDirection }>(
    () =>
      filter === "all"
        ? { key: "layer", direction: "asc" }
        : filter === "qualified" || filter === "low_liquidity"
        ? { key: "score", direction: "desc" }
        : { key: "symbol", direction: "asc" },
    [filter]
  );
  const [sort, setSort] = useState(defaultSort);

  useEffect(() => {
    setSort(defaultSort);
  }, [defaultSort]);

  const filtered = useMemo(() => {
    if (filter === "all") return rows;
    return rows.filter((row) => row.layer === filter);
  }, [rows, filter]);

  const sortedRows = useMemo(() => {
    const statusRank: Record<UnifiedAuditRow["status"], number> = {
      skipped: 0,
      rejected: 1,
      qualified: 2,
    };
    const layerRank: Record<UnifiedAuditRow["layer"], number> = {
      universe_rejected: 0,
      no_data: 1,
      tradability_rejected: 2,
      no_setup: 3,
      low_liquidity: 4,
      qualified: 5,
    };

    return [...filtered].sort((a, b) => {
      let result = 0;

      switch (sort.key) {
        case "symbol":
          result = compareText(a.symbol, b.symbol);
          break;
        case "layer":
          result = layerRank[a.layer] - layerRank[b.layer];
          break;
        case "status":
          result = statusRank[a.status] - statusRank[b.status];
          break;
        case "liquidity_archetype":
          result = compareText(a.liquidity_archetype, b.liquidity_archetype);
          break;
        case "setup_type":
          result = compareText(a.setup_type, b.setup_type);
          break;
        case "price":
          result =
            sortableNumber(a.price, sort.direction) -
            sortableNumber(b.price, sort.direction);
          break;
        case "volume_1h_usdt":
          result =
            sortableNumber(a.volume_1h_usdt, sort.direction) -
            sortableNumber(b.volume_1h_usdt, sort.direction);
          break;
        case "threshold_volume_1h_usdt":
          result =
            sortableNumber(a.threshold_volume_1h_usdt, sort.direction) -
            sortableNumber(b.threshold_volume_1h_usdt, sort.direction);
          break;
        case "volume_24h_usdt":
          result =
            sortableNumber(a.volume_24h_usdt, sort.direction) -
            sortableNumber(b.volume_24h_usdt, sort.direction);
          break;
        case "threshold_volume_24h_usdt":
          result =
            sortableNumber(a.threshold_volume_24h_usdt, sort.direction) -
            sortableNumber(b.threshold_volume_24h_usdt, sort.direction);
          break;
        case "price_change_pct_24h":
          result =
            sortableNumber(a.price_change_pct_24h, sort.direction) -
            sortableNumber(b.price_change_pct_24h, sort.direction);
          break;
        case "market_quality_score":
          result =
            sortableNumber(a.market_quality_score, sort.direction) -
            sortableNumber(b.market_quality_score, sort.direction);
          break;
        case "net_quality_score":
          result =
            sortableNumber(a.net_quality_score, sort.direction) -
            sortableNumber(b.net_quality_score, sort.direction);
          break;
        case "reason":
          result = compareText(a.reason_code ?? a.reason_text, b.reason_code ?? b.reason_text);
          break;
        case "score":
          result =
            sortableNumber(a.score, sort.direction) -
            sortableNumber(b.score, sort.direction);
          break;
      }

      if (result === 0) {
        result = compareText(a.symbol, b.symbol);
      }

      return result * (sort.direction === "asc" ? 1 : -1);
    });
  }, [filtered, sort]);

  if (filtered.length === 0)
    return (
      <p className="py-4 text-sm text-slate-500">
        No symbols in this category.
      </p>
    );

  return (
    <div className="table-shell overflow-x-auto">
      <div className="min-w-[106rem]">
        <div className="grid grid-cols-[6rem_8rem_6rem_6rem_7rem_5rem_7rem_7rem_7rem_7rem_6rem_6rem_6rem_1fr_5rem] gap-3 border-b border-slate-200 bg-slate-50 px-4 py-2 text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">
          <SortHeader
            label="Symbol"
            sortKey="symbol"
            activeSort={sort}
            onSort={(key) =>
              setSort((current) => toggleSort(current, key, auditSortDirection(key)))
            }
          />
          <SortHeader
            label="Layer"
            sortKey="layer"
            activeSort={sort}
            onSort={(key) =>
              setSort((current) => toggleSort(current, key, auditSortDirection(key)))
            }
          />
          <SortHeader
            label="Status"
            sortKey="status"
            activeSort={sort}
            onSort={(key) =>
              setSort((current) => toggleSort(current, key, auditSortDirection(key)))
            }
          />
          <SortHeader
            label="Class"
            sortKey="liquidity_archetype"
            activeSort={sort}
            onSort={(key) =>
              setSort((current) => toggleSort(current, key, auditSortDirection(key)))
            }
          />
          <SortHeader
            label="Setup"
            sortKey="setup_type"
            activeSort={sort}
            onSort={(key) =>
              setSort((current) => toggleSort(current, key, auditSortDirection(key)))
            }
          />
          <SortHeader
            label="Price"
            sortKey="price"
            activeSort={sort}
            onSort={(key) =>
              setSort((current) => toggleSort(current, key, auditSortDirection(key)))
            }
            align="right"
          />
          <SortHeader
            label="1h Vol"
            sortKey="volume_1h_usdt"
            activeSort={sort}
            onSort={(key) =>
              setSort((current) => toggleSort(current, key, auditSortDirection(key)))
            }
            align="right"
          />
          <SortHeader
            label="Vol Threshold"
            sortKey="threshold_volume_1h_usdt"
            activeSort={sort}
            onSort={(key) =>
              setSort((current) => toggleSort(current, key, auditSortDirection(key)))
            }
            align="right"
          />
          <SortHeader
            label="24h Vol"
            sortKey="volume_24h_usdt"
            activeSort={sort}
            onSort={(key) =>
              setSort((current) => toggleSort(current, key, auditSortDirection(key)))
            }
            align="right"
          />
          <SortHeader
            label="24h Floor"
            sortKey="threshold_volume_24h_usdt"
            activeSort={sort}
            onSort={(key) =>
              setSort((current) => toggleSort(current, key, auditSortDirection(key)))
            }
            align="right"
          />
          <SortHeader
            label="24h Chg"
            sortKey="price_change_pct_24h"
            activeSort={sort}
            onSort={(key) =>
              setSort((current) => toggleSort(current, key, auditSortDirection(key)))
            }
            align="right"
          />
          <SortHeader
            label="Quality"
            sortKey="market_quality_score"
            activeSort={sort}
            onSort={(key) =>
              setSort((current) => toggleSort(current, key, auditSortDirection(key)))
            }
            align="right"
          />
          <SortHeader
            label="Net"
            sortKey="net_quality_score"
            activeSort={sort}
            onSort={(key) =>
              setSort((current) => toggleSort(current, key, auditSortDirection(key)))
            }
            align="right"
          />
          <SortHeader
            label="Reason"
            sortKey="reason"
            activeSort={sort}
            onSort={(key) =>
              setSort((current) => toggleSort(current, key, auditSortDirection(key)))
            }
          />
          <SortHeader
            label="Score"
            sortKey="score"
            activeSort={sort}
            onSort={(key) =>
              setSort((current) => toggleSort(current, key, auditSortDirection(key)))
            }
            align="right"
          />
        </div>
        {sortedRows.map((row, idx) => (
          <div
            key={`${row.symbol}-${idx}`}
            className="grid grid-cols-[6rem_8rem_6rem_6rem_7rem_5rem_7rem_7rem_7rem_7rem_6rem_6rem_6rem_1fr_5rem] items-center gap-3 border-b border-slate-100 px-4 py-2.5 text-sm last:border-b-0"
          >
            <span className="flex items-center gap-2 font-medium text-slate-900">
              <CoinIcon symbol={row.symbol} size={18} />
              {row.symbol.replace("USDT", "")}
            </span>
            <span>
              <span
                className={cn(
                  "inline-block rounded px-1.5 py-0.5 text-[10px] font-medium",
                  LAYER_META[row.layer].tone
                )}
              >
                {LAYER_META[row.layer].label}
              </span>
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
            <span>
              <LiquidityArchetypeBadge archetype={row.liquidity_archetype} />
            </span>
            <span className="text-xs text-slate-600">
              {row.setup_type?.replace(/_/g, " ") ?? "-"}
            </span>
            <span className="text-right tabular-nums text-slate-600">
              {row.price != null ? `$${formatNumber(row.price, row.price < 1 ? 4 : 2)}` : "-"}
            </span>
            <span className="text-right tabular-nums text-slate-600">
              {formatCurrency(row.volume_1h_usdt, true)}
            </span>
            <span className="text-right tabular-nums text-slate-600">
              {formatCurrency(row.threshold_volume_1h_usdt, true)}
            </span>
            <span className="text-right tabular-nums text-slate-600">
              {formatCurrency(row.volume_24h_usdt, true)}
            </span>
            <span className="text-right tabular-nums text-slate-600">
              {formatCurrency(row.threshold_volume_24h_usdt, true)}
            </span>
            <span
              className={cn(
                "text-right tabular-nums",
                row.price_change_pct_24h == null
                  ? "text-slate-400"
                  : row.price_change_pct_24h >= 0
                    ? "text-emerald-700"
                    : "text-red-700"
              )}
            >
              {row.price_change_pct_24h == null
                ? "-"
                : formatPercent(row.price_change_pct_24h / 100)}
            </span>
            <span className="text-right tabular-nums text-slate-600">
              {row.market_quality_score != null
                ? formatNumber(row.market_quality_score * 100, 0)
                : "-"}
            </span>
            <span className="text-right tabular-nums text-slate-600">
              {row.net_quality_score != null
                ? formatNumber(row.net_quality_score * 100, 0)
                : "-"}
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
    </div>
  );
}

export default function ScanAuditPage() {
  const [scanResult, setScanResult] = useState<ManualScanResponse | null>(null);
  const [scanning, setScanning] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshResult, setRefreshResult] = useState<ScannerRefreshResponse | null>(null);
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

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const refreshed = await refreshScannerLiveData();
      setRefreshResult(refreshed);
      const result = await runManualScan(interval, 15);
      setScanResult(result);
      setActiveFilter("all");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  }, [interval]);

  const auditRows = useMemo(() => scanResult?.audit_rows ?? [], [scanResult]);
  const candidates = useMemo(
    () => scanResult?.candidate_evaluations ?? [],
    [scanResult]
  );
  const candidateBySymbol = useMemo(
    () => new Map(candidates.map((candidate) => [candidate.symbol, candidate])),
    [candidates]
  );
  const tableRows = useMemo<UnifiedAuditRow[]>(() => {
    const universeRejectedRows: UnifiedAuditRow[] = candidates
      .filter((candidate) => !candidate.tradability_passed)
      .map((candidate) => ({
        symbol: candidate.symbol,
        status: "rejected",
        layer: "universe_rejected",
        reason_code: candidate.reason_codes[0] ?? null,
        reason_text: candidate.reason_text || "Rejected during universe tradability filtering",
        setup_type: null,
        movement_quality: candidate.metrics,
        score: 0,
        liquidity_archetype: candidate.liquidity_archetype,
        price: candidate.price,
        volume_1h_usdt: candidate.volume_1h_usdt,
        threshold_volume_1h_usdt: candidate.threshold_volume_1h_usdt,
        volume_24h_usdt: candidate.volume_24h_usdt,
        threshold_volume_24h_usdt: candidate.threshold_volume_24h_usdt,
        price_change_pct_24h: candidate.price_change_pct_24h,
        market_quality_score: candidate.market_quality_score,
        net_quality_score: null,
      }));

    const downstreamRows: UnifiedAuditRow[] = auditRows.map((row) => {
      const candidate = candidateBySymbol.get(row.symbol);
      return {
        ...row,
        layer: classifyAuditLayer(row),
        liquidity_archetype: row.liquidity_archetype ?? candidate?.liquidity_archetype ?? null,
        price: candidate?.price ?? null,
        volume_1h_usdt: row.volume_1h_usdt ?? candidate?.volume_1h_usdt ?? null,
        threshold_volume_1h_usdt:
          row.threshold_volume_1h_usdt ?? candidate?.threshold_volume_1h_usdt ?? null,
        volume_24h_usdt: candidate?.volume_24h_usdt ?? null,
        threshold_volume_24h_usdt:
          row.threshold_volume_24h_usdt ?? candidate?.threshold_volume_24h_usdt ?? null,
        price_change_pct_24h: candidate?.price_change_pct_24h ?? null,
        market_quality_score: candidate?.market_quality_score ?? null,
        net_quality_score: row.net_quality_score ?? null,
      };
    });

    return [...universeRejectedRows, ...downstreamRows];
  }, [auditRows, candidateBySymbol, candidates]);

  const layerCounts = useMemo(() => {
    return {
      all: tableRows.length,
      universe_rejected: tableRows.filter((row) => row.layer === "universe_rejected").length,
      no_data: tableRows.filter((row) => row.layer === "no_data").length,
      tradability_rejected: tableRows.filter((row) => row.layer === "tradability_rejected").length,
      no_setup: tableRows.filter((row) => row.layer === "no_setup").length,
      low_liquidity: tableRows.filter((row) => row.layer === "low_liquidity").length,
      qualified: tableRows.filter((row) => row.layer === "qualified").length,
    };
  }, [tableRows]);

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
              onClick={handleRefresh}
              disabled={refreshing || scanning}
              className={buttonClassName("secondary", "md")}
            >
              {refreshing ? "Refreshing..." : "Refresh Binance"}
            </button>
            <button
              onClick={handleScan}
              disabled={scanning || refreshing}
              className={buttonClassName("primary", "md")}
            >
              {scanning ? "Scanning..." : "Run scan"}
            </button>
          </div>
        }
      />

      {error ? <p className="text-sm text-red-700">{error}</p> : null}
      {refreshResult ? (
        <p className="text-xs text-slate-500">
          Binance refresh loaded {formatNumber(refreshResult.symbols_refreshed, 0)} symbols across{" "}
          {formatNumber(refreshResult.successful_pairs, 0)}/
          {formatNumber(refreshResult.requested_pairs, 0)} symbol-interval pairs.
        </p>
      ) : null}

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

          <ScanAuditTable rows={tableRows} filter={activeFilter} />

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
