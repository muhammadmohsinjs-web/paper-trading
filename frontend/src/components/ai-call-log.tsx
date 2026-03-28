"use client";

import { LocalDateTime } from "@/components/local-date-time";
import { formatCurrency, formatNumber, formatPercent } from "@/lib/format";
import { cn } from "@/lib/format";
import type { StrategyWithStats } from "@/lib/types";

type AICallLogProps = {
  strategy: StrategyWithStats;
  executionMessage?: string | null;
};

type FindingEntry = {
  label: string;
  value: string;
};

function toneForStatus(status: string | null | undefined) {
  const normalized = (status ?? "").toLowerCase();
  if (normalized.includes("error") || normalized.includes("failed")) {
    return "text-red-700";
  }
  if (
    normalized.includes("success") ||
    normalized.includes("executed") ||
    normalized.includes("completed") ||
    normalized.includes("signal") ||
    normalized.includes("validated")
  ) {
    return "text-emerald-700";
  }
  if (normalized.includes("skipped") || normalized.includes("hold") || normalized.includes("rejected")) {
    return "text-amber-700";
  }
  return "text-slate-900";
}

function toTitleCase(value: string) {
  return value
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatFindingValue(value: unknown) {
  if (typeof value === "number") {
    if (value >= 0 && value <= 1) {
      return formatPercent(value * 100, 1);
    }
    return formatNumber(value, 3);
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (value === null || value === undefined) {
    return "--";
  }
  return String(value);
}

function extractFindings(raw: string | null | undefined) {
  const trimmed = raw?.trim();
  if (!trimmed) {
    return { summary: "", entries: [] as FindingEntry[], paragraphs: [] as string[] };
  }

  if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
    try {
      const parsed = JSON.parse(trimmed) as Record<string, unknown>;
      if (!Array.isArray(parsed) && typeof parsed === "object" && parsed !== null) {
        const summaryKeys = ["reason", "rationale", "explanation", "summary", "analysis"];
        const summary =
          summaryKeys
            .map((key) => parsed[key])
            .find((value): value is string => typeof value === "string" && value.trim().length > 0) ?? "";

        const entries = Object.entries(parsed)
          .filter(([key]) => !summaryKeys.includes(key))
          .slice(0, 6)
          .map(([key, value]) => ({
            label: toTitleCase(key),
            value: formatFindingValue(value)
          }));

        return { summary, entries, paragraphs: [] as string[] };
      }
    } catch {
      // Fall through to plain-text formatting.
    }
  }

  const lines = trimmed
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);

  return {
    summary: lines[0] ?? "",
    entries: [] as FindingEntry[],
    paragraphs: lines.slice(1)
  };
}

function DefinitionList({
  items
}: {
  items: Array<{ label: string; value: React.ReactNode; tone?: string }>;
}) {
  return (
    <dl className="space-y-3">
      {items.map((item) => (
        <div key={item.label} className="flex items-start justify-between gap-4 text-sm">
          <dt className="text-slate-500">{item.label}</dt>
          <dd className={cn("text-right font-medium text-slate-900", item.tone)}>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function AICallLog({ strategy, executionMessage }: AICallLogProps) {
  const findings = extractFindings(strategy.ai_last_reasoning);
  const lastStatus = strategy.ai_last_decision_status ?? "No recent call";
  const lastProvider = strategy.ai_last_provider || strategy.ai_provider || "--";
  const lastModel = strategy.ai_last_model || strategy.ai_model || "--";

  return (
    <section className="space-y-4">
      <div className="space-y-1">
        <h3 className="text-lg font-semibold text-slate-900">AI telemetry</h3>
        <p className="text-sm text-slate-600">
          Latest inference, usage, and reasoning details.
        </p>
      </div>

      <div className="grid gap-8 lg:grid-cols-2">
        <DefinitionList
          items={[
            { label: "Status", value: lastStatus, tone: toneForStatus(strategy.ai_last_decision_status) },
            { label: "Provider", value: lastProvider },
            { label: "Model", value: lastModel },
            { label: "Cooldown", value: `${formatNumber(strategy.ai_cooldown_seconds, 0)}s` },
            { label: "Prompt tokens", value: formatNumber(strategy.ai_last_prompt_tokens, 0) },
            { label: "Completion tokens", value: formatNumber(strategy.ai_last_completion_tokens, 0) },
            { label: "Total tokens", value: formatNumber(strategy.ai_last_total_tokens, 0) },
            { label: "Last cost", value: formatCurrency(strategy.ai_last_cost_usdt), tone: "text-blue-700" }
          ]}
        />

        <DefinitionList
          items={[
            { label: "Total calls", value: formatNumber(strategy.ai_total_calls, 0) },
            { label: "Total tokens", value: formatNumber(strategy.ai_total_tokens, 0) },
            { label: "Total cost", value: formatCurrency(strategy.ai_total_cost_usdt), tone: "text-blue-700" },
            {
              label: "Last updated",
              value: strategy.ai_last_decision_at ? <LocalDateTime value={strategy.ai_last_decision_at} /> : "--"
            }
          ]}
        />
      </div>

      {executionMessage ? (
        <p className="text-sm text-slate-600">
          Latest response <span className="font-medium text-slate-900">{executionMessage}</span>
        </p>
      ) : null}

      <div className="space-y-3 border-t border-slate-200 pt-4">
        <div className="flex items-center justify-between gap-4">
          <h4 className="text-sm font-semibold text-slate-900">Last findings</h4>
          <span className="text-xs text-slate-500">From `ai_last_reasoning`</span>
        </div>

        {findings.summary ? (
          <p className="text-sm leading-7 text-slate-900">{findings.summary}</p>
        ) : (
          <p className="text-sm text-slate-500">No findings recorded yet.</p>
        )}

        {findings.entries.length ? (
          <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {findings.entries.map((entry) => (
              <div key={entry.label}>
                <dt className="text-[11px] uppercase tracking-[0.12em] text-slate-400">{entry.label}</dt>
                <dd className="mt-1 text-sm font-medium text-slate-900">{entry.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}

        {findings.paragraphs.length ? (
          <div className="space-y-2">
            {findings.paragraphs.map((paragraph, index) => (
              <p key={`${paragraph}-${index}`} className="text-sm leading-7 text-slate-600">
                {paragraph.replace(/^[-*]\s*/, "")}
              </p>
            ))}
          </div>
        ) : null}

        {strategy.ai_last_reasoning ? (
          <details>
            <summary className="cursor-pointer text-xs text-slate-500 transition hover:text-slate-700">
              Show raw response
            </summary>
            <pre className="mt-2 max-h-56 overflow-auto bg-slate-50 p-3 text-xs text-slate-600">
              {strategy.ai_last_reasoning}
            </pre>
          </details>
        ) : null}
      </div>
    </section>
  );
}
