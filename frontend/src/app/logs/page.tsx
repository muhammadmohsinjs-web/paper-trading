import { getAILogs, getAILogStats, getOpenAIUsage } from "@/lib/api";
import { AILogsTable } from "@/components/ai-logs-table";
import { OpenAIUsagePanel } from "@/components/openai-usage-panel";
import { MetricStrip, PageHeader } from "@/components/ui";

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
      <PageHeader
        title="API call history"
        description="Complete audit trail of every AI decision, including successful, skipped, and failed calls."
      />

      <MetricStrip
        items={[
          { label: "Total calls", value: String(stats.total_calls) },
          { label: "Actual API calls", value: String(stats.success), tone: "success" },
          { label: "Skipped", value: String(stats.skipped), tone: "warning" },
          { label: "Errors", value: String(stats.errors), tone: "danger" },
          {
            label: "Estimated cost",
            value: `$${stats.total_cost_usdt.toFixed(4)}`,
            tone: "accent"
          },
          { label: "Total tokens", value: stats.total_tokens.toLocaleString() }
        ]}
      />

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
