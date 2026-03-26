"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { LivePrice } from "@/components/live-price";
import { useLiveFeed } from "@/hooks/use-live-feed";
import { formatCurrency, formatNumber } from "@/lib/format";
import type { DashboardResponse, EngineStatus, MarketPrice, SignalData } from "@/lib/types";
import { SignalMeter } from "@/components/signal-meter";
import { StrategyCard } from "@/components/strategy-card";
import { CreateStrategyDialog } from "@/components/create-strategy-dialog";

type DashboardClientProps = {
  dashboard: DashboardResponse;
  marketPrice: MarketPrice | null;
  engineStatus: EngineStatus | null;
  initialSignal: SignalData | null;
  backendError?: string | null;
};

export function DashboardClient({
  dashboard,
  marketPrice,
  engineStatus,
  initialSignal,
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
      return "No active loops";
    }

    return runningStrategies
      .map((strategyId) => strategyNameById.get(strategyId) ?? `Strategy ${strategyId.slice(0, 8)}`)
      .join(", ");
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

  const multicoinStrategies = useMemo(
    () =>
      dashboard.strategies.filter((strategy) => strategy.execution_mode === "multi_coin_shared_wallet").length,
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

  const statRows = [
    {
      label: "Running Loops",
      value: formatNumber(engineStatus?.count ?? 0, 0),
      detail: runningLoopDetail,
      valueClass: "text-rise",
      borderClass: "border-rise/30"
    },
    {
      label: "AI Calls",
      value: formatNumber(dashboard.ai_total_calls, 0),
      detail: "AI is used as a targeted reviewer, not as a full-universe scanner.",
      valueClass: "text-gold",
      borderClass: "border-gold/30"
    },
    {
      label: "Active Strategies",
      value: formatNumber(dashboard.active_strategies, 0),
      detail: "Shared-wallet and single-symbol modes can run side by side.",
      valueClass: "text-sand",
      borderClass: "border-white/12"
    },
    {
      label: "Consensus Picks",
      value: formatNumber(consensusPicks.length, 0),
      detail: consensusPicks.map((pick) => pick.symbol).join(" · ") || "No picks persisted yet",
      valueClass: "text-gold",
      borderClass: "border-gold/20"
    }
  ];

  return (
    <div className="page-stage rise-in">
      {backendError ? (
        <section className="panel border border-fall/30 bg-fall/[0.06] p-5">
          <p className="text-xs uppercase tracking-[0.24em] text-fall">Backend Unavailable</p>
          <p className="mt-3 text-sm leading-6 text-mist/75">
            The dashboard is showing fallback data because the frontend could not reach the backend API.
            Check that the FastAPI server is running on `127.0.0.1:8000`. Latest error: {backendError}
          </p>
        </section>
      ) : null}

      <section className="panel min-w-0 overflow-hidden p-0">
        <div className="border-b border-white/6 px-6 py-5">
          <p className="text-xs uppercase tracking-[0.3em] text-gold">Operating Overview</p>
          <h2 className="mt-3 text-4xl font-semibold text-sand">Portfolio Desk</h2>
          <p className="mt-3 max-w-3xl text-sm leading-7 text-mist/66">
            Live wallet equity, execution state, and market context for the active multicoin desk.
          </p>
        </div>

        <div className="grid min-w-0 gap-8 px-6 py-6 xl:grid-cols-[minmax(0,1.45fr)_minmax(24rem,0.95fr)]">
          <div className="min-w-0 space-y-6">
            <div className="grid gap-5 lg:grid-cols-3">
              <div className="min-w-0 border-b border-white/8 pb-4">
                <p className="text-[10px] uppercase tracking-[0.24em] text-mist/42">Total Equity</p>
                <p className="mt-3 text-[clamp(2.2rem,3.4vw,3.3rem)] font-semibold leading-none tracking-[-0.055em] text-sand">
                  {formatCurrency(totalEquity)}
                </p>
              </div>
              <div className="min-w-0 border-b border-white/8 pb-4">
                <p className="text-[10px] uppercase tracking-[0.24em] text-mist/42">Open Positions</p>
                <p className="mt-3 text-[clamp(2.2rem,3.4vw,3.3rem)] font-semibold leading-none tracking-[-0.055em] text-sand">
                  {formatNumber(openPositions, 0)}
                </p>
              </div>
              <div className="min-w-0 border-b border-white/8 pb-4">
                <p className="text-[10px] uppercase tracking-[0.24em] text-mist/42">Portfolio Strategies</p>
                <p className="mt-3 text-[clamp(2.2rem,3.4vw,3.3rem)] font-semibold leading-none tracking-[-0.055em] text-sand">
                  {formatNumber(multicoinStrategies, 0)}
                </p>
              </div>
            </div>

            <div className="grid gap-6 border-t border-white/6 pt-5 lg:grid-cols-[minmax(0,1fr)_16rem]">
              <div className="min-w-0">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
                  <div className="min-w-0">
                    <p className="text-[10px] uppercase tracking-[0.24em] text-mist/42">Execution Context</p>
                    <p className="mt-2 text-lg font-semibold text-sand">{activeStatusLabel}</p>
                  </div>
                  <div className="rounded-full border border-white/10 px-3 py-1 text-xs uppercase tracking-[0.2em] text-mist/65">
                    {live.connected ? "WebSocket live" : "Snapshot feed"}
                  </div>
                </div>
                <p className="mt-4 max-w-4xl break-words text-sm leading-7 text-mist/62">
                  {runningLoopDetail}
                </p>
                {focusSymbols.length ? (
                  <div className="mt-4 flex flex-wrap gap-2">
                    {focusSymbols.map((symbol) => (
                      <span
                        key={symbol}
                        className="rounded-full border border-white/10 bg-black/15 px-3 py-1 text-xs uppercase tracking-[0.16em] text-mist/72"
                      >
                        {symbol}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="min-w-0 border-white/8 lg:border-l lg:pl-6">
                <p className="text-[10px] uppercase tracking-[0.24em] text-mist/42">Desk Snapshot</p>
                <div className="mt-4 space-y-4 text-sm text-mist/68">
                  <div className="flex items-center justify-between gap-4 border-b border-white/6 pb-3">
                    <span>Tracked symbols</span>
                    <span className="text-sand">{focusSymbols.length || 1}</span>
                  </div>
                  <div className="flex items-center justify-between gap-4 border-b border-white/6 pb-3">
                    <span>Strategy count</span>
                    <span className="text-sand">{formatNumber(dashboard.total_strategies, 0)}</span>
                  </div>
                  <div className="flex items-center justify-between gap-4 border-b border-white/6 pb-3">
                    <span>AI cost</span>
                    <span className="text-gold">{formatCurrency(dashboard.ai_total_cost_usdt)}</span>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <span>Selection state</span>
                    <span className="text-sand">{consensusPicks.length ? "Ready" : "Pending"}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="grid gap-0 overflow-hidden rounded-[1.7rem] border border-white/8 bg-white/[0.02] sm:grid-cols-2">
              {statRows.map((item, index) => (
                <div
                  key={item.label}
                  className={`min-w-0 px-5 py-4 ${
                    index % 2 === 0 ? "sm:border-r sm:border-white/6" : ""
                  } ${index < 2 ? "border-b border-white/6" : ""}`}
                >
                  <div className={`mb-3 inline-flex border-b pb-1 text-[10px] uppercase tracking-[0.22em] text-mist/44 ${item.borderClass}`}>
                    {item.label}
                  </div>
                  <p className={`text-[clamp(2rem,2.8vw,2.8rem)] font-semibold leading-none tracking-[-0.05em] ${item.valueClass}`}>
                    {item.value}
                  </p>
                  <p className="mt-3 break-words text-sm leading-6 text-mist/60">{item.detail}</p>
                </div>
              ))}
            </div>
          </div>

          <aside className="min-w-0 border-t border-white/6 pt-5 xl:border-l xl:border-t-0 xl:pl-8 xl:pt-0">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p className="text-xs uppercase tracking-[0.28em] text-gold">Market Anchor</p>
                <h3 className="mt-3 text-[clamp(2.6rem,4vw,4.2rem)] font-semibold leading-none tracking-[-0.055em] text-sand">
                  <LivePrice price={latestPrice} className="text-sand" />
                </h3>
                <p className="mt-4 max-w-md text-sm leading-7 text-mist/62">
                  BTCUSDT is the regime anchor for the desk. Entry review is restricted to the persisted multicoin watchlist.
                </p>
              </div>
              <span
                className={`rounded-full px-3 py-1 text-xs uppercase tracking-[0.2em] ${
                  live.connected ? "bg-rise/12 text-rise" : "bg-white/8 text-mist/60"
                }`}
              >
                {live.connected ? "Live" : "Standby"}
              </span>
            </div>

            <div className="mt-6 grid gap-2 border-t border-white/6 pt-4 text-sm text-mist/66">
              <div className="flex items-center justify-between gap-4">
                <span>AI spend</span>
                <span className="text-gold">{formatCurrency(dashboard.ai_total_cost_usdt)}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Total calls</span>
                <span className="text-sand">{formatNumber(dashboard.ai_total_calls, 0)}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Strategies</span>
                <span className="text-sand">{formatNumber(dashboard.total_strategies, 0)}</span>
              </div>
              <div className="flex items-center justify-between gap-4">
                <span>Consensus symbols</span>
                <span className="text-sand">{formatNumber(consensusPicks.length, 0)}</span>
              </div>
            </div>

            <div className="mt-6 flex flex-wrap items-center gap-3">
              {compareTargets.length === 2 ? (
                <Link
                  href={`/compare?a=${compareTargets[0]}&b=${compareTargets[1]}`}
                  className="rounded-full border border-gold/35 bg-gold/10 px-4 py-2 text-sm text-gold transition hover:bg-gold/16"
                >
                  Compare leading strategies
                </Link>
              ) : null}
              <button
                onClick={() => setShowCreate(true)}
                className="rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm text-sand transition hover:border-gold/30 hover:text-gold"
              >
                Create new strategy
              </button>
            </div>
          </aside>
        </div>
      </section>

      <section className="grid min-w-0 gap-6 xl:grid-cols-[0.92fr,1.08fr]">
        <SignalMeter symbol="BTCUSDT" interval="1h" initialSignal={initialSignal} />

        <div className="panel min-w-0 p-6 rise-in-delay">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div className="min-w-0">
              <p className="text-xs uppercase tracking-[0.28em] text-gold">Daily Universe</p>
              <h3 className="mt-3 text-2xl font-semibold text-sand">Consensus Watchlist</h3>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-mist/62">
                These symbols appear most often across persisted strategy watchlists. This is an entry universe,
                not a forced-trade list.
              </p>
            </div>
            <p className="break-words text-sm text-mist/55">
              Focus symbols {focusSymbols.join(" · ") || "not established yet"}
            </p>
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
            {consensusPicks.length ? (
              consensusPicks.map((pick) => (
                <div key={pick.symbol} className="rounded-[1.4rem] border border-white/8 bg-black/15 p-4">
                  <p className="text-[10px] uppercase tracking-[0.24em] text-mist/40">Watchlist</p>
                  <p className="mt-3 text-xl font-semibold text-sand">{pick.symbol}</p>
                  <p className="mt-2 text-sm text-mist/58">
                    Listed in {pick.count} strategy{pick.count === 1 ? "" : "ies"}
                  </p>
                  <p className="mt-1 text-xs uppercase tracking-[0.16em] text-gold/80">
                    Best rank #{pick.bestRank}
                  </p>
                </div>
              ))
            ) : multicoinStrategies === 0 ? (
              <div className="sm:col-span-2 xl:col-span-5 rounded-[1.5rem] border border-dashed border-gold/20 bg-gold/[0.04] p-6 text-sm text-mist/62">
                No shared-wallet strategy is live in the current database. Create one to get the initial `1000 USDT`
                wallet state and persisted daily picks on the desk.
              </div>
            ) : (
              <div className="sm:col-span-2 xl:col-span-5 rounded-[1.5rem] border border-dashed border-white/10 bg-black/10 p-6 text-sm text-mist/58">
                Persisted daily picks will appear here after the selector runs.
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="min-w-0 space-y-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-[0.24em] text-mist/50">Strategy Registry</p>
            <h2 className="text-3xl font-semibold text-sand">Execution Desks</h2>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-mist/60">
              Each strategy is presented as a workspace entry with wallet health, watchlist context, and execution mode.
            </p>
          </div>
          <div className="flex items-center gap-4">
            <p className="text-sm text-mist/60">Total AI spend {formatCurrency(dashboard.ai_total_cost_usdt)}</p>
            <button
              onClick={() => setShowCreate(true)}
              className="rounded-full bg-gold/90 px-4 py-2 text-sm font-medium text-black transition hover:bg-gold"
            >
              + New Strategy
            </button>
          </div>
        </div>

        <div className="space-y-4">
          {dashboard.strategies.length ? (
            dashboard.strategies.map((strategy) => <StrategyCard key={strategy.id} strategy={strategy} />)
          ) : (
            <div className="panel border-dashed p-8 text-sm text-mist/58">
              No strategies yet. Create one to start building a shared-wallet multicoin desk.
            </div>
          )}
        </div>
      </section>

      <CreateStrategyDialog
        open={showCreate}
        onClose={() => setShowCreate(false)}
        existingStrategies={dashboard.strategies}
      />
    </div>
  );
}
