"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createStrategy } from "@/lib/api";
import { STRATEGY_TYPE_META, type StrategyType, type StrategyWithStats } from "@/lib/types";
import { buttonClassName } from "@/components/ui";

const STRATEGY_TYPES = Object.keys(STRATEGY_TYPE_META) as StrategyType[];

const DEFAULT_CONFIGS: Record<StrategyType, Record<string, unknown>> = {
  sma_crossover: {
    strategy_type: "sma_crossover",
    sma_short: 10,
    sma_long: 50,
    initial_balance: 1000,
    interval_seconds: 300,
  },
  rsi_mean_reversion: {
    strategy_type: "rsi_mean_reversion",
    rsi_period: 14,
    rsi_oversold: 30,
    rsi_overbought: 70,
    initial_balance: 1000,
    interval_seconds: 300,
  },
  macd_momentum: {
    strategy_type: "macd_momentum",
    macd_fast: 12,
    macd_slow: 26,
    macd_signal: 9,
    initial_balance: 1000,
    interval_seconds: 300,
  },
  bollinger_bounce: {
    strategy_type: "bollinger_bounce",
    bb_period: 20,
    bb_std_dev: 2.0,
    initial_balance: 1000,
    interval_seconds: 300,
  },
  hybrid_composite: {
    strategy_type: "hybrid_composite",
    sma_short: 10,
    sma_long: 50,
    confidence_gate: 0.5,
    initial_balance: 1000,
    interval_seconds: 300,
    ai_enabled: true,
    ai_cooldown_seconds: 300,
    ai_max_tokens: 700,
    ai_temperature: 0.2,
  },
};

type Props = {
  open: boolean;
  onClose: () => void;
  existingStrategies?: StrategyWithStats[];
};

export function CreateStrategyDialog({ open, onClose, existingStrategies = [] }: Props) {
  const router = useRouter();
  const [selectedType, setSelectedType] = useState<StrategyType>("sma_crossover");
  const [executionMode, setExecutionMode] = useState<"single_symbol" | "multi_coin_shared_wallet">("multi_coin_shared_wallet");
  const [name, setName] = useState("");
  const [balance, setBalance] = useState(1000);
  const [autoStart, setAutoStart] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const meta = STRATEGY_TYPE_META[selectedType];

  const existingTypes = new Set(
    existingStrategies.map((s) => s.config_json?.strategy_type as string).filter(Boolean)
  );
  const isDuplicate = existingTypes.has(selectedType);

  async function handleCreate() {
    if (!name.trim()) {
      setError("Strategy name is required");
      return;
    }
    setLoading(true);
    setError(null);

    try {
      const config = {
        ...DEFAULT_CONFIGS[selectedType],
        initial_balance: balance,
        execution_mode: executionMode,
        primary_symbol: "BTCUSDT",
        top_pick_count: 5,
        max_concurrent_positions: 2,
      };
      await createStrategy({
        name: name.trim(),
        description: meta.description,
        config_json: config,
        execution_mode: executionMode,
        primary_symbol: "BTCUSDT",
        top_pick_count: 5,
        max_concurrent_positions: 2,
        is_active: autoStart,
        ai_enabled: selectedType === "hybrid_composite",
      });
      setName("");
      setBalance(1000);
      setAutoStart(false);
      setSelectedType("sma_crossover");
      setExecutionMode("multi_coin_shared_wallet");
      onClose();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create strategy");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/30 px-4 backdrop-blur-sm">
      <div className="w-full max-w-xl rounded-[18px] border border-slate-200 bg-white p-6 shadow-[0_12px_40px_rgba(15,23,42,0.14)]">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Create Strategy</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-900">New Desk</h2>
          </div>
          <button
            onClick={onClose}
            className={buttonClassName("tertiary", "sm")}
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M6 6l8 8M14 6l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {/* Strategy type selector */}
        <div className="mt-5 space-y-2">
          <label className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Strategy Type</label>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {STRATEGY_TYPES.map((type) => {
              const m = STRATEGY_TYPE_META[type];
              const isSelected = type === selectedType;
              const alreadyExists = existingTypes.has(type);
              return (
                <button
                  key={type}
                  onClick={() => {
                    setSelectedType(type);
                    if (!name.trim() || Object.values(STRATEGY_TYPE_META).some(v => v.label === name)) {
                      setName(m.label);
                    }
                  }}
                  className={`relative rounded-lg border px-3 py-2.5 text-left text-xs transition ${
                    isSelected
                      ? `${m.color} shadow-sm`
                      : "border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900"
                  }`}
                >
                  {alreadyExists && (
                    <span className="absolute -right-1.5 -top-1.5 rounded-full border border-slate-200 bg-white px-1.5 py-0.5 text-[9px] font-medium text-slate-500">
                      Active
                    </span>
                  )}
                  <span className="font-medium">{m.short}</span>
                  <p className="mt-0.5 text-[10px] opacity-70">{m.label}</p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Name */}
        <div className="mt-4 space-y-1.5">
          <label className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={meta.label}
            className="w-full rounded-[10px] border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-blue-300 focus:outline-none"
          />
        </div>

        {/* Balance */}
        <div className="mt-4 space-y-1.5">
          <label className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Initial Balance (USDT)</label>
          <input
            type="number"
            value={balance}
            onChange={(e) => setBalance(Number(e.target.value))}
            min={100}
            max={100000}
            step={100}
            className="w-full rounded-[10px] border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-blue-300 focus:outline-none"
          />
        </div>

        <div className="mt-4 space-y-2">
          <label className="text-[11px] font-medium uppercase tracking-[0.14em] text-slate-500">Execution Mode</label>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button"
              onClick={() => setExecutionMode("multi_coin_shared_wallet")}
              className={`rounded-lg border px-3 py-2 text-left text-xs transition ${
                executionMode === "multi_coin_shared_wallet"
                  ? "border-blue-200 bg-blue-50 text-blue-700"
                  : "border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900"
              }`}
            >
              <span className="font-medium">Multi-Coin</span>
              <p className="mt-0.5 text-[10px] opacity-70">Shared wallet, daily top 5 picks, max 2 positions</p>
            </button>
            <button
              type="button"
              onClick={() => setExecutionMode("single_symbol")}
              className={`rounded-lg border px-3 py-2 text-left text-xs transition ${
                executionMode === "single_symbol"
                  ? "border-blue-200 bg-blue-50 text-blue-700"
                  : "border-slate-200 text-slate-600 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900"
              }`}
            >
              <span className="font-medium">Single Symbol</span>
              <p className="mt-0.5 text-[10px] opacity-70">Legacy mode centered on BTCUSDT</p>
            </button>
          </div>
        </div>

        {/* Description preview */}
        <div className="mt-4 rounded-[12px] border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs text-slate-600">{meta.description}</p>
          {selectedType === "hybrid_composite" && (
            <p className="mt-1 text-xs text-blue-700">
              AI-enabled — will make API calls (costs apply)
            </p>
          )}
          {executionMode === "multi_coin_shared_wallet" && (
            <p className="mt-1 text-xs text-emerald-700">
              Multi-coin mode will scan the dynamic liquid universe and trade from the daily top picks.
            </p>
          )}
        </div>

        {/* Auto-start toggle */}
        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={() => setAutoStart(!autoStart)}
            className={`relative h-5 w-9 rounded-full transition ${
              autoStart ? "bg-emerald-600" : "bg-slate-300"
            }`}
          >
            <span
              className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white transition-transform ${
              autoStart ? "translate-x-4" : ""
              }`}
            />
          </button>
          <span className="text-sm text-slate-600">Start trading immediately</span>
        </div>

        {/* Duplicate warning */}
        {isDuplicate && (
          <div className="mt-3 rounded-[10px] border border-amber-200 bg-amber-50 px-3 py-2">
            <p className="text-xs text-amber-700">
              You already have a <strong>{meta.label}</strong> strategy running. Consider adjusting your existing one instead.
            </p>
          </div>
        )}

        {/* Error */}
        {error && (
          <p className="mt-3 text-xs text-red-700">{error}</p>
        )}

        {/* Actions */}
        <div className="mt-6 flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className={buttonClassName("secondary", "md")}
          >
            Cancel
          </button>
          <button
            onClick={handleCreate}
            disabled={loading}
            className={`rounded-[10px] px-5 py-2 text-sm font-medium transition disabled:opacity-50 ${
              isDuplicate
                ? "border border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100"
                : "bg-blue-700 text-white hover:bg-blue-800"
            }`}
          >
            {loading ? "Creating..." : isDuplicate ? "Create Anyway" : "Create Strategy"}
          </button>
        </div>
      </div>
    </div>
  );
}
