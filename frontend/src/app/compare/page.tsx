import { ComparisonBoard } from "@/components/comparison-board";
import { MetricStrip, PageHeader } from "@/components/ui";
import { getEquityCurve, getStrategies } from "@/lib/api";

type ComparePageProps = {
  searchParams?: { a?: string; b?: string };
};

export default async function ComparePage({ searchParams }: ComparePageProps) {
  const strategies = await getStrategies();
  if (strategies.length < 2) {
    return (
      <div className="text-sm text-slate-600">
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
      <PageHeader
        title="Side-by-side strategy review"
        description="Evaluate equity curves and operating metrics for two isolated strategy wallets."
      />

      <MetricStrip
        items={[
          { label: "Left desk", value: left.name },
          { label: "Right desk", value: right.name },
          { label: "Compared strategies", value: "2" }
        ]}
      />

      <ComparisonBoard left={left} right={right} leftEquity={leftEquity} rightEquity={rightEquity} />
    </div>
  );
}
