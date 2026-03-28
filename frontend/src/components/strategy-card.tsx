"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { formatCurrency, formatPercent } from "@/lib/format";
import { toggleStrategy } from "@/lib/api";
import type { StrategyWithStats } from "@/lib/types";
import { CoinIcon } from "@/components/ui";

type StrategyRowProps = {
  strategy: StrategyWithStats;
};

export function StrategyRow({ strategy }: StrategyRowProps) {
  const router = useRouter();
  const [toggling, setToggling] = useState(false);
  const combinedPnl = strategy.total_pnl + (strategy.has_open_position ? (strategy.unrealized_pnl ?? 0) : 0);
  const executionMode = strategy.execution_mode ?? "single_symbol";
  const primarySymbol = strategy.primary_symbol ?? "BTCUSDT";
  const intendedSymbols = strategy.daily_picks?.map((pick) => pick.symbol).filter(Boolean) ?? [];
  const targetLabel =
    executionMode === "multi_coin_shared_wallet"
      ? intendedSymbols.length
        ? intendedSymbols.join(", ")
        : strategy.focus_symbol ?? "Pending picks"
      : primarySymbol;

  async function handleToggle(event: React.MouseEvent<HTMLButtonElement>) {
    event.preventDefault();
    event.stopPropagation();
    if (toggling) return;

    setToggling(true);
    try {
      await toggleStrategy(strategy.id, !strategy.is_active);
      router.refresh();
    } catch {
      // Refresh will reflect the next successful state change.
    } finally {
      setToggling(false);
    }
  }

  return (
    <tr>
      <td className="font-medium text-slate-900">
        <Link href={`/strategies/${strategy.id}`} className="transition hover:text-blue-700">
          {strategy.name}
        </Link>
      </td>
      <td>
        <span className="flex flex-wrap items-center gap-1.5">
          {executionMode === "multi_coin_shared_wallet" && intendedSymbols.length
            ? intendedSymbols.map((sym, i) => (
                <span key={sym} className="inline-flex items-center gap-1">
                  <CoinIcon symbol={sym} size={16} />
                  <span>{sym.replace("USDT", "")}</span>
                  {i < intendedSymbols.length - 1 ? "," : ""}
                </span>
              ))
            : <><CoinIcon symbol={targetLabel} size={16} />{targetLabel}</>}
        </span>
      </td>
      <td className="font-medium text-slate-900">{formatCurrency(strategy.total_equity)}</td>
      <td className={combinedPnl >= 0 ? "text-emerald-700" : "text-red-700"}>
        {formatCurrency(combinedPnl)}
      </td>
      <td>{formatPercent(strategy.win_rate)}</td>
      <td>{strategy.open_positions_count ?? 0}</td>
      <td>
        <button
          type="button"
          onClick={handleToggle}
          disabled={toggling}
          className="inline-flex items-center gap-2 text-sm text-slate-700 disabled:opacity-60"
        >
          <span
            className={`h-2.5 w-2.5 rounded-full ${
              strategy.is_active ? "bg-emerald-500" : "bg-slate-300"
            }`}
          />
          {toggling ? "Updating..." : strategy.is_active ? "Active" : "Paused"}
        </button>
      </td>
    </tr>
  );
}

export const StrategyCard = StrategyRow;
