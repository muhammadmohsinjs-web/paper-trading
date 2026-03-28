import { LeaderboardTable } from "@/components/leaderboard-table";
import { MetricStrip, PageHeader } from "@/components/ui";
import { getLeaderboard } from "@/lib/api";

type LeaderboardPageProps = {
  searchParams?: { sort_by?: string };
};

export default async function LeaderboardPage({ searchParams }: LeaderboardPageProps) {
  const sortBy = searchParams?.sort_by ?? "total_pnl";
  const entries = await getLeaderboard(sortBy);
  const topEntry = entries[0];
  const profitable = entries.filter((entry) => entry.total_pnl > 0).length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Ranked strategies"
        description="Compare performance by P&L, win rate, trade count, and equity."
      />

      <MetricStrip
        items={[
          { label: "Top strategy", value: topEntry?.strategy_name ?? "--" },
          { label: "Profitable desks", value: String(profitable) },
          { label: "Ranked entries", value: String(entries.length) }
        ]}
      />

      <LeaderboardTable entries={entries} />
    </div>
  );
}
