import { getAILogs, getAILogStats, getOpenAIUsage } from "@/lib/api";
import { AILogsTable } from "@/components/ai-logs-table";
import { OpenAIUsagePanel } from "@/components/openai-usage-panel";

type LogsPageProps = {
  searchParams?: { status?: string; strategy_id?: string; page?: string };
};

export default async function LogsPage({ searchParams }: LogsPageProps) {
  const page = Math.max(1, parseInt(searchParams?.page ?? "1", 10));
  const limit = 50;
  const offset = (page - 1) * limit;

  const [logsData, stats, openaiUsage] = await Promise.all([
    getAILogs({
      status: searchParams?.status,
      strategy_id: searchParams?.strategy_id,
      limit,
      offset,
    }),
    getAILogStats(),
    getOpenAIUsage(7).catch(() => null),
  ]);

  return (
    <div className="space-y-6">
      <section className="panel p-6">
        <p className="text-xs uppercase tracking-[0.28em] text-gold">AI Logs</p>
        <h2 className="mt-2 text-3xl font-semibold text-sand">API Call History</h2>
        <p className="mt-2 text-sm text-mist/65">
          Complete audit trail of every AI decision — successful, skipped, and failed calls.
        </p>
      </section>

      {/* Stats cards */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <div className="panel p-4 text-center">
          <p className="text-2xl font-semibold text-sand">{stats.total_calls}</p>
          <p className="mt-1 text-xs text-mist/60">Total Calls</p>
        </div>
        <div className="panel p-4 text-center">
          <p className="text-2xl font-semibold text-green-400">{stats.success}</p>
          <p className="mt-1 text-xs text-mist/60">Actual API Calls</p>
        </div>
        <div className="panel p-4 text-center">
          <p className="text-2xl font-semibold text-amber-400">{stats.skipped}</p>
          <p className="mt-1 text-xs text-mist/60">Skipped</p>
        </div>
        <div className="panel p-4 text-center">
          <p className="text-2xl font-semibold text-red-400">{stats.errors}</p>
          <p className="mt-1 text-xs text-mist/60">Errors</p>
        </div>
        <div className="panel p-4 text-center">
          <p className="text-2xl font-semibold text-gold">${stats.total_cost_usdt.toFixed(4)}</p>
          <p className="mt-1 text-xs text-mist/60">Est. Cost</p>
        </div>
        <div className="panel p-4 text-center">
          <p className="text-2xl font-semibold text-sand">{stats.total_tokens.toLocaleString()}</p>
          <p className="mt-1 text-xs text-mist/60">Total Tokens</p>
        </div>
      </div>

      {/* OpenAI real usage panel */}
      {openaiUsage && <OpenAIUsagePanel data={openaiUsage} />}

      <AILogsTable
        logs={logsData.logs}
        total={logsData.total}
        page={page}
        limit={limit}
        currentStatus={searchParams?.status}
        currentStrategyId={searchParams?.strategy_id}
      />
    </div>
  );
}
