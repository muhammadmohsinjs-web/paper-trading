"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { LivePrice } from "@/components/live-price";
import { MarketScanner } from "@/components/market-scanner";
import { StrategyRow } from "@/components/strategy-card";
import { CreateStrategyDialog } from "@/components/create-strategy-dialog";
import { useLiveFeed } from "@/hooks/use-live-feed";
import { backendBaseUrl } from "@/lib/env";
import { formatCurrency, formatNumber } from "@/lib/format";
import type { DashboardResponse, EngineStatus, MarketPrice } from "@/lib/types";
import { MetricStrip, PageHeader, CoinIcon, buttonClassName } from "@/components/ui";

type DashboardClientProps = {
  dashboard: DashboardResponse;
  marketPrice: MarketPrice | null;
  engineStatus: EngineStatus | null;
  backendError?: string | null;
};

export function DashboardClient({
  dashboard,
  marketPrice,
  engineStatus,
  backendError
}: DashboardClientProps) {
  const live = useLiveFeed();
  const [showCreate, setShowCreate] = useState(false);

  const latestPrice =
    live.latestPriceBySymbol[marketPrice?.symbol ?? "BTCUSDT"] ?? marketPrice?.price ?? null;

  const strategyNameById = useMemo(
    () => new Map(dashboard.strategies.map((strategy) => [strategy.id, strategy.name])),
    [dashboard.strategies]
  );

  const runningLoopDetail = useMemo(() => {
    const runningStrategies = engineStatus?.running_strategies ?? [];
    if (!runningStrategies.length) {
      return "No active loops.";
    }

    return runningStrategies
      .map((strategyId) => strategyNameById.get(strategyId) ?? `Strategy ${strategyId.slice(0, 8)}`)
      .join(" · ");
  }, [engineStatus?.running_strategies, strategyNameById]);

  const compareTargets = useMemo(
    () => dashboard.strategies.slice(0, 2).map((strategy) => strategy.id),
    [dashboard.strategies]
  );

  const totalEquity = useMemo(
    () => dashboard.strategies.reduce((sum, strategy) => sum + (strategy.total_equity ?? 0), 0),
    [dashboard.strategies]
  );

  const openPositions = useMemo(
    () => dashboard.strategies.reduce((sum, strategy) => sum + (strategy.open_positions_count ?? 0), 0),
    [dashboard.strategies]
  );

  const consensusPicks = useMemo(() => {
    const counts = new Map<string, { count: number; bestRank: number }>();

    for (const strategy of dashboard.strategies) {
      for (const pick of strategy.daily_picks ?? []) {
        const current = counts.get(pick.symbol);
        counts.set(pick.symbol, {
          count: (current?.count ?? 0) + 1,
          bestRank: current ? Math.min(current.bestRank, pick.rank) : pick.rank
        });
      }
    }

    return Array.from(counts.entries())
      .map(([symbol, meta]) => ({ symbol, ...meta }))
      .sort(
        (left, right) =>
          right.count - left.count ||
          left.bestRank - right.bestRank ||
          left.symbol.localeCompare(right.symbol)
      )
      .slice(0, 5);
  }, [dashboard.strategies]);

  const focusSymbols = useMemo(() => {
    return dashboard.strategies
      .filter((strategy) => strategy.is_active)
      .map((strategy) => strategy.focus_symbol ?? strategy.primary_symbol ?? "BTCUSDT")
      .filter((value, index, values) => values.indexOf(value) === index)
      .slice(0, 4);
  }, [dashboard.strategies]);

  const activeStatusLabel = engineStatus?.count
    ? `${formatNumber(engineStatus.count, 0)} loops active`
    : "Execution standby";

  return (
    <div className="page-stage rise-in">
      {backendError ? (
        <div className="flex items-start gap-3 rounded-xl border border-red-200/80 bg-red-50/60 p-4">
          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-red-100 text-red-600">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M6 3.5v3M6 8.5h.005" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
          </span>
          <div>
            <p className="text-sm font-medium text-red-800">Backend unavailable</p>
            <p className="mt-1 text-sm leading-6 text-red-700/80">
              Showing fallback data. Check that the server is running at <code className="rounded bg-red-100 px-1 py-0.5 text-xs">{backendBaseUrl}</code>
            </p>
          </div>
        </div>
      ) : null}

      <PageHeader
        title="Overview"
        actions={
          <button onClick={() => setShowCreate(true)} className={buttonClassName("primary", "md")}>
            Create strategy
          </button>
        }
      />

      <MetricStrip
        items={[
          { label: "Total equity", value: formatCurrency(totalEquity) },
          { label: "Open positions", value: formatNumber(openPositions, 0) },
          { label: "Active strategies", value: formatNumber(dashboard.active_strategies, 0) },
          {
            label: "Status",
            value: activeStatusLabel,
            tone: engineStatus?.count ? "success" : "warning"
          }
        ]}
      />

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="rounded-xl border border-slate-200/60 bg-white p-5 space-y-4">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <h2 className="text-base font-semibold text-slate-900">Execution context</h2>
              <p className="text-sm leading-6 text-slate-500">{runningLoopDetail}</p>
            </div>
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${
              live.connected
                ? "bg-emerald-50 text-emerald-700"
                : "bg-slate-100 text-slate-500"
            }`}>
              <span className={`h-1.5 w-1.5 rounded-full ${live.connected ? "bg-emerald-500" : "bg-slate-400"}`} />
              {live.connected ? "Live" : "Snapshot"}
            </span>
          </div>

          {focusSymbols.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
              <span className="text-[11px] font-medium uppercase tracking-[0.1em] text-slate-400">Focus</span>
              {focusSymbols.map((sym) => (
                <span
                  key={sym}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-700"
                >
                  <CoinIcon symbol={sym} size={14} />
                  {sym.replace("USDT", "")}
                </span>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-xl border border-slate-200/60 bg-gradient-to-br from-slate-900 to-slate-800 p-5 space-y-4 text-white">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-400">
              Market anchor
            </p>
            <div className="mt-2 text-3xl font-semibold tracking-[-0.04em]">
              <LivePrice price={latestPrice} className="text-white" />
            </div>
          </div>

          <dl className="space-y-2.5 text-sm border-t border-white/10 pt-4">
            <div className="flex items-center justify-between gap-4">
              <dt className="text-slate-400">Tracked symbols</dt>
              <dd className="font-medium">{focusSymbols.length || 1}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-slate-400">Strategy count</dt>
              <dd className="font-medium">{formatNumber(dashboard.total_strategies, 0)}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-slate-400">AI spend</dt>
              <dd className="font-medium">
                {formatCurrency(dashboard.ai_total_cost_usdt)}
              </dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt className="text-slate-400">Selection state</dt>
              <dd className="font-medium">
                {consensusPicks.length ? "Ready" : "Pending"}
              </dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="grid gap-4 xl:grid-cols-[0.82fr,1.18fr]">
        <div className="rounded-xl border border-slate-200/60 bg-white p-5 space-y-4">
          <div className="space-y-1">
            <h2 className="text-base font-semibold text-slate-900">Consensus watchlist</h2>
            <p className="text-sm leading-6 text-slate-500">
              Top symbols across strategy watchlists.
            </p>
          </div>

          <div className="space-y-2">
            {consensusPicks.length ? (
              consensusPicks.map((pick, i) => (
                <div
                  key={pick.symbol}
                  className="flex items-center justify-between gap-4 rounded-lg bg-slate-50/80 px-3.5 py-3"
                >
                  <div className="flex items-center gap-3">
                    <span className="flex h-6 w-6 items-center justify-center rounded-md bg-slate-200/60 text-[11px] font-semibold text-slate-500">
                      {i + 1}
                    </span>
                    <CoinIcon symbol={pick.symbol} />
                    <div>
                      <p className="text-sm font-medium text-slate-900">{pick.symbol.replace("USDT", "")}</p>
                      <p className="text-[11px] text-slate-400">
                        {pick.count} {pick.count === 1 ? "strategy" : "strategies"}
                      </p>
                    </div>
                  </div>
                  <span className="rounded-md bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-600">
                    Rank #{pick.bestRank}
                  </span>
                </div>
              ))
            ) : (
              <div className="rounded-lg bg-slate-50/80 px-4 py-6 text-center text-sm text-slate-400">
                {dashboard.strategies.some(
                  (strategy) => strategy.execution_mode === "multi_coin_shared_wallet"
                )
                  ? "Picks will appear after the selector runs."
                  : "No shared-wallet strategy is live yet."}
              </div>
            )}
          </div>
        </div>

        <MarketScanner />
      </section>

      <section className="space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-1">
            <h2 className="text-base font-semibold text-slate-900">Strategies</h2>
            <p className="text-sm text-slate-500">
              Active desks, wallet state, and live status.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            {compareTargets.length === 2 ? (
              <Link
                href={`/compare?a=${compareTargets[0]}&b=${compareTargets[1]}`}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:border-slate-300 hover:text-slate-900"
              >
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M5 2v10M9 2v10" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/><path d="M2 5.5h5M7 8.5h5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
                Compare
              </Link>
            ) : null}
          </div>
        </div>

        {dashboard.strategies.length ? (
          <div className="table-shell overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Targets</th>
                  <th>Equity</th>
                  <th>P&amp;L</th>
                  <th>Win Rate</th>
                  <th>Positions</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {dashboard.strategies.map((strategy) => (
                  <StrategyRow key={strategy.id} strategy={strategy} />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-slate-200 bg-slate-50/50 py-10 text-center">
            <p className="text-sm text-slate-400">No strategies yet.</p>
            <p className="mt-1 text-xs text-slate-400">Create one to start building a trading desk.</p>
          </div>
        )}
      </section>

      <CreateStrategyDialog
        open={showCreate}
        onClose={() => setShowCreate(false)}
        existingStrategies={dashboard.strategies}
      />
    </div>
  );
}
