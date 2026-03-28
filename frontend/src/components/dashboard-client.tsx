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
import { MetricStrip, PageHeader, Surface, buttonClassName } from "@/components/ui";

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
        <Surface className="border-red-200 bg-red-50 p-5">
          <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-red-700">
            Backend unavailable
          </p>
          <p className="mt-3 text-sm leading-6 text-slate-700">
            The dashboard is showing fallback data because the frontend could not reach the backend API.
            Check that the FastAPI server is running at `{backendBaseUrl}`. Latest error: {backendError}
          </p>
        </Surface>
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

      <section className="grid gap-8 border-t border-slate-200 pt-6 xl:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="min-w-0 space-y-4">
          <div className="space-y-2">
            <h2 className="text-lg font-semibold text-slate-900">Execution context</h2>
            <p className="text-sm leading-7 text-slate-600">{runningLoopDetail}</p>
          </div>
          <p className="text-sm text-slate-500">
            Feed {live.connected ? "WebSocket live" : "Snapshot"} · Focus{" "}
            {focusSymbols.length ? focusSymbols.join(" · ") : "not established yet"}
          </p>
        </div>

        <div className="min-w-0 space-y-4 xl:border-l xl:border-slate-200 xl:pl-6">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-400">
              Market anchor
            </p>
            <div className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-slate-900">
              <LivePrice price={latestPrice} className="text-slate-900" />
            </div>
          </div>

          <dl className="space-y-3 text-sm text-slate-600">
            <div className="flex items-center justify-between gap-4">
              <dt>Tracked symbols</dt>
              <dd className="font-medium text-slate-900">{focusSymbols.length || 1}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt>Strategy count</dt>
              <dd className="font-medium text-slate-900">{formatNumber(dashboard.total_strategies, 0)}</dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt>AI spend</dt>
              <dd className="font-medium text-slate-900">
                {formatCurrency(dashboard.ai_total_cost_usdt)}
              </dd>
            </div>
            <div className="flex items-center justify-between gap-4">
              <dt>Selection state</dt>
              <dd className="font-medium text-slate-900">
                {consensusPicks.length ? "Ready" : "Pending"}
              </dd>
            </div>
          </dl>
        </div>
      </section>

      <section className="grid gap-10 xl:grid-cols-[0.82fr,1.18fr]">
        <div className="min-w-0 space-y-4">
          <div className="space-y-2">
            <h2 className="text-lg font-semibold text-slate-900">Consensus watchlist</h2>
            <p className="text-sm leading-6 text-slate-600">
              Symbols appearing most often across persisted strategy watchlists.
            </p>
          </div>

          <div className="divide-y divide-slate-200 border-y border-slate-200">
            {consensusPicks.length ? (
              consensusPicks.map((pick) => (
                <div key={pick.symbol} className="flex items-center justify-between gap-4 py-4">
                  <div>
                    <p className="font-medium text-slate-900">{pick.symbol}</p>
                    <p className="text-sm text-slate-500">
                      Listed in {pick.count} strategy{pick.count === 1 ? "" : "ies"}
                    </p>
                  </div>
                  <p className="text-sm text-slate-500">Best rank #{pick.bestRank}</p>
                </div>
              ))
            ) : (
              <div className="py-6 text-sm text-slate-500">
                {dashboard.strategies.some(
                  (strategy) => strategy.execution_mode === "multi_coin_shared_wallet"
                )
                  ? "Persisted daily picks will appear here after the selector runs."
                  : "No shared-wallet strategy is live in the current database yet."}
              </div>
            )}
          </div>
        </div>

        <MarketScanner />
      </section>

      <section className="space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-1">
            <h2 className="text-lg font-semibold text-slate-900">Strategies</h2>
            <p className="text-sm text-slate-600">
              Active desks, wallet state, and live operating status in one table.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-sm">
            {compareTargets.length === 2 ? (
              <Link
                href={`/compare?a=${compareTargets[0]}&b=${compareTargets[1]}`}
                className="text-slate-500 transition hover:text-slate-900"
              >
                Compare leading strategies
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
          <div className="border-t border-slate-200 py-6 text-sm text-slate-500">
            No strategies yet. Create one to start building a shared-wallet desk.
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
