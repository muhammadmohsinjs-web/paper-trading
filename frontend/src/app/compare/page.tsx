import { ComparisonBoard } from "@/components/comparison-board";
import { getEquityCurve, getStrategies } from "@/lib/api";

type ComparePageProps = {
  searchParams?: { a?: string; b?: string };
};

export default async function ComparePage({ searchParams }: ComparePageProps) {
  const strategies = await getStrategies();
  if (strategies.length < 2) {
    return (
      <div className="panel p-6 text-sm text-mist/65">
        At least two strategies are required before comparison becomes useful.
      </div>
    );
  }

  const leftId = searchParams?.a ?? strategies[0].id;
  const rightId = searchParams?.b ?? strategies[1].id;
  const left = strategies.find((strategy) => strategy.id === leftId) ?? strategies[0];
  const right =
    strategies.find((strategy) => strategy.id === rightId && strategy.id !== left.id) ??
    strategies.find((strategy) => strategy.id !== left.id) ??
    strategies[1];

  const [leftEquity, rightEquity] = await Promise.all([
    getEquityCurve(left.id),
    getEquityCurve(right.id)
  ]);

  return (
    <div className="space-y-6">
      <section className="panel p-6">
        <p className="text-xs uppercase tracking-[0.28em] text-gold">Comparison</p>
        <h2 className="mt-2 text-3xl font-semibold text-sand">Side-by-Side Strategy Review</h2>
        <p className="mt-2 text-sm text-mist/65">
          Evaluate equity curves and operating metrics for two isolated strategy wallets.
        </p>
      </section>

      <ComparisonBoard left={left} right={right} leftEquity={leftEquity} rightEquity={rightEquity} />
    </div>
  );
}
