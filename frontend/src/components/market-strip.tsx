import { formatCurrency, formatNumber } from "@/lib/format";
import { StatusPill } from "@/components/status-pill";

type MarketStripProps = {
  symbol: string;
  price: number;
  runningCount: number;
  activeStrategies: number;
  aiStrategies: number;
};

export function MarketStrip({
  symbol,
  price,
  runningCount,
  activeStrategies,
  aiStrategies
}: MarketStripProps) {
  return (
    <section className="mb-8 grid gap-4 lg:grid-cols-[1.6fr_repeat(3,1fr)]">
      <div className="rounded-[28px] border border-white/10 bg-panel p-5">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-xs uppercase tracking-[0.28em] text-mist/55">Live Market</div>
            <div className="mt-2 text-3xl font-semibold text-sand">{symbol}</div>
            <div className="mt-2 text-sm text-mist/70">
              Primary feed for pricing, paper execution, and chart overlays.
            </div>
          </div>
          <div className="text-right">
            <div className="text-3xl font-semibold text-rise">{formatCurrency(price)}</div>
            <div className="mt-2 text-xs uppercase tracking-[0.22em] text-mist/55">
              {formatNumber(price, 2)} USD
            </div>
          </div>
        </div>
      </div>
      <div className="rounded-[24px] border border-white/10 bg-panel/80 p-5">
        <div className="text-xs uppercase tracking-[0.22em] text-mist/55">Engine</div>
        <div className="mt-3 text-3xl font-semibold">{runningCount}</div>
        <div className="mt-2">
          <StatusPill tone="rise">{runningCount > 0 ? "Running" : "Idle"}</StatusPill>
        </div>
      </div>
      <div className="rounded-[24px] border border-white/10 bg-panel/80 p-5">
        <div className="text-xs uppercase tracking-[0.22em] text-mist/55">Active Strategies</div>
        <div className="mt-3 text-3xl font-semibold">{activeStrategies}</div>
        <div className="mt-2 text-sm text-mist/65">Strategy loops enabled in backend.</div>
      </div>
      <div className="rounded-[24px] border border-white/10 bg-panel/80 p-5">
        <div className="text-xs uppercase tracking-[0.22em] text-mist/55">AI Strategies</div>
        <div className="mt-3 text-3xl font-semibold">{aiStrategies}</div>
        <div className="mt-2 text-sm text-mist/65">Claude-backed strategies in circulation.</div>
      </div>
    </section>
  );
}
