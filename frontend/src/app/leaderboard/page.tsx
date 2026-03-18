import { LeaderboardTable } from "@/components/leaderboard-table";
import { getLeaderboard } from "@/lib/api";

type LeaderboardPageProps = {
  searchParams?: { sort_by?: string };
};

export default async function LeaderboardPage({ searchParams }: LeaderboardPageProps) {
  const sortBy = searchParams?.sort_by ?? "total_pnl";
  const entries = await getLeaderboard(sortBy);

  return (
    <div className="space-y-6">
      <section className="panel p-6">
        <p className="text-xs uppercase tracking-[0.28em] text-gold">Leaderboard</p>
        <h2 className="mt-2 text-3xl font-semibold text-sand">Ranked Strategies</h2>
        <p className="mt-2 text-sm text-mist/65">
          Compare overall performance by P&amp;L, win rate, trade count, and equity.
        </p>
      </section>

      <LeaderboardTable entries={entries} />
    </div>
  );
}
