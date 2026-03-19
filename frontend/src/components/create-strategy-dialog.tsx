"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createStrategy } from "@/lib/api";
import { STRATEGY_TYPE_META, type StrategyType } from "@/lib/types";

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
};

export function CreateStrategyDialog({ open, onClose }: Props) {
  const router = useRouter();
  const [selectedType, setSelectedType] = useState<StrategyType>("sma_crossover");
  const [name, setName] = useState("");
  const [balance, setBalance] = useState(1000);
  const [autoStart, setAutoStart] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const meta = STRATEGY_TYPE_META[selectedType];

  async function handleCreate() {
    if (!name.trim()) {
      setError("Strategy name is required");
      return;
    }
    setLoading(true);
    setError(null);

    try {
      const config = { ...DEFAULT_CONFIGS[selectedType], initial_balance: balance };
      await createStrategy({
        name: name.trim(),
        description: meta.description,
        config_json: config,
        is_active: autoStart,
        ai_enabled: selectedType === "hybrid_composite",
      });
      setName("");
      setBalance(1000);
      setAutoStart(false);
      setSelectedType("sma_crossover");
      onClose();
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create strategy");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-xl border border-white/10 bg-[#0d1117] p-6 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h2 className="text-xl font-semibold text-sand">New Strategy</h2>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-mist/60 transition hover:bg-white/10 hover:text-sand"
          >
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
              <path d="M6 6l8 8M14 6l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        </div>

        {/* Strategy type selector */}
        <div className="mt-5 space-y-2">
          <label className="text-xs uppercase tracking-[0.2em] text-mist/50">Strategy Type</label>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            {STRATEGY_TYPES.map((type) => {
              const m = STRATEGY_TYPE_META[type];
              const isSelected = type === selectedType;
              return (
                <button
                  key={type}
                  onClick={() => {
                    setSelectedType(type);
                    if (!name.trim() || Object.values(STRATEGY_TYPE_META).some(v => v.label === name)) {
                      setName(m.label);
                    }
                  }}
                  className={`rounded-lg border px-3 py-2.5 text-left text-xs transition ${
                    isSelected
                      ? `${m.color} border-current`
                      : "border-white/10 text-mist/60 hover:border-white/20 hover:text-mist"
                  }`}
                >
                  <span className="font-medium">{m.short}</span>
                  <p className="mt-0.5 text-[10px] opacity-70">{m.label}</p>
                </button>
              );
            })}
          </div>
        </div>

        {/* Name */}
        <div className="mt-4 space-y-1.5">
          <label className="text-xs uppercase tracking-[0.2em] text-mist/50">Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={meta.label}
            className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-sand placeholder:text-mist/30 focus:border-gold/40 focus:outline-none"
          />
        </div>

        {/* Balance */}
        <div className="mt-4 space-y-1.5">
          <label className="text-xs uppercase tracking-[0.2em] text-mist/50">Initial Balance (USDT)</label>
          <input
            type="number"
            value={balance}
            onChange={(e) => setBalance(Number(e.target.value))}
            min={100}
            max={100000}
            step={100}
            className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-sand focus:border-gold/40 focus:outline-none"
          />
        </div>

        {/* Description preview */}
        <div className="mt-4 rounded-lg border border-white/5 bg-white/[0.02] px-3 py-2">
          <p className="text-xs text-mist/50">{meta.description}</p>
          {selectedType === "hybrid_composite" && (
            <p className="mt-1 text-xs text-gold/70">
              AI-enabled — will make API calls (costs apply)
            </p>
          )}
        </div>

        {/* Auto-start toggle */}
        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={() => setAutoStart(!autoStart)}
            className={`relative h-5 w-9 rounded-full transition ${
              autoStart ? "bg-rise" : "bg-white/15"
            }`}
          >
            <span
              className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white transition-transform ${
                autoStart ? "translate-x-4" : ""
              }`}
            />
          </button>
          <span className="text-sm text-mist/70">Start trading immediately</span>
        </div>

        {/* Error */}
        {error && (
          <p className="mt-3 text-xs text-fall">{error}</p>
        )}

        {/* Actions */}
        <div className="mt-6 flex items-center justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded-lg border border-white/10 px-4 py-2 text-sm text-mist/60 transition hover:bg-white/5 hover:text-sand"
          >
            Cancel
          </button>
          <button
            onClick={handleCreate}
            disabled={loading}
            className="rounded-lg bg-gold/90 px-5 py-2 text-sm font-medium text-black transition hover:bg-gold disabled:opacity-50"
          >
            {loading ? "Creating..." : "Create Strategy"}
          </button>
        </div>
      </div>
    </div>
  );
}
