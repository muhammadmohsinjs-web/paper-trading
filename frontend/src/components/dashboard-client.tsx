"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { LivePrice } from "@/components/live-price";
import { useLiveFeed } from "@/hooks/use-live-feed";
import { formatCurrency, formatNumber } from "@/lib/format";
import type { DashboardResponse, EngineStatus, MarketPrice } from "@/lib/types";
import { MetricCard } from "@/components/metric-card";
import { SignalMeter } from "@/components/signal-meter";
import { StrategyCard } from "@/components/strategy-card";
import { CreateStrategyDialog } from "@/components/create-strategy-dialog";

type DashboardClientProps = {
  dashboard: DashboardResponse;
  marketPrice: MarketPrice | null;
  engineStatus: EngineStatus | null;
};

export function DashboardClient({
  dashboard,
  marketPrice,
  engineStatus
}: DashboardClientProps) {
  const live = useLiveFeed();
  const [showCreate, setShowCreate] = useState(false);
  useEffect(() => {
    for (const strategy of dashboard.strategies) {
      if (!strategy.is_active) {
        console.info("[dashboard] inactive strategy", {
          id: strategy.id,
          name: strategy.name,
        });
      }
    }
  }, [dashboard.strategies]);

  const latestPrice =
    live.latestPriceBySymbol[marketPrice?.symbol ?? "BTCUSDT"] ?? marketPrice?.price ?? null;
  const strategyNameById = useMemo(
    () =>
      new Map(dashboard.strategies.map((strategy) => [strategy.id, strategy.name])),
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

  return (
    <div className="space-y-8">
      <section className="grid gap-6 lg:grid-cols-[1.25fr,0.75fr]">
        <div className="panel p-6">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
            <div className="space-y-3">
              <p className="text-xs uppercase tracking-[0.3em] text-gold">Live Market</p>
              <h2>
                <LivePrice price={latestPrice} className="text-sand" />
              </h2>
              <p className="text-sm text-mist/65">
                BTCUSDT live price {live.connected ? "streaming over WebSocket" : "using latest API snapshot"}.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <span
                className={`rounded-full px-3 py-1 text-xs uppercase tracking-[0.2em] ${
                  live.connected
                    ? "bg-rise/12 text-rise"
                    : "bg-white/8 text-mist/60"
                }`}
              >
                {live.connected ? "Live" : "Standby"}
              </span>
              {compareTargets.length === 2 ? (
                <Link
                  href={`/compare?a=${compareTargets[0]}&b=${compareTargets[1]}`}
                  className="rounded-full border border-gold/40 px-4 py-2 text-sm text-gold transition hover:bg-gold/10"
                >
                  Compare Top 2
                </Link>
              ) : null}
            </div>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <MetricCard label="Strategies" value={formatNumber(dashboard.total_strategies, 0)} />
          <MetricCard label="Active" value={formatNumber(dashboard.active_strategies, 0)} accent="rise" />
          <MetricCard label="AI Calls" value={formatNumber(dashboard.ai_total_calls, 0)} accent="gold" />
          <MetricCard
            label="Running Loops"
            value={formatNumber(engineStatus?.count ?? 0, 0)}
            detail={runningLoopDetail}
          />
        </div>
      </section>

      <section>
        <SignalMeter symbol="BTCUSDT" interval="1h" />
      </section>

      <section className="space-y-4">
        <div className="flex items-end justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-mist/50">Dashboard Home</p>
            <h2 className="text-2xl font-semibold text-sand">Strategy Grid</h2>
          </div>
          <div className="flex items-center gap-4">
            <p className="text-sm text-mist/60">
              Total AI spend {formatCurrency(dashboard.ai_total_cost_usdt)}
            </p>
            <button
              onClick={() => setShowCreate(true)}
              className="rounded-lg bg-gold/90 px-4 py-2 text-sm font-medium text-black transition hover:bg-gold"
            >
              + New Strategy
            </button>
          </div>
        </div>

        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {dashboard.strategies.map((strategy) => (
            <StrategyCard key={strategy.id} strategy={strategy} />
          ))}
        </div>
      </section>

      <CreateStrategyDialog open={showCreate} onClose={() => setShowCreate(false)} existingStrategies={dashboard.strategies} />
    </div>
  );
}
