"use client";

import { formatCurrency, formatDateTime, formatNumber, formatPercent } from "@/lib/format";
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
    return "text-fall";
  }
  if (
    normalized.includes("success") ||
    normalized.includes("executed") ||
    normalized.includes("completed") ||
    normalized.includes("signal") ||
    normalized.includes("validated")
  ) {
    return "text-rise";
  }
  if (normalized.includes("skipped") || normalized.includes("hold") || normalized.includes("rejected")) {
    return "text-gold";
  }
  return "text-gold";
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
        const summary = summaryKeys
          .map((key) => parsed[key])
          .find((value): value is string => typeof value === "string" && value.trim().length > 0) ?? "";

        const entries = Object.entries(parsed)
          .filter(([key]) => !summaryKeys.includes(key))
          .slice(0, 6)
          .map(([key, value]) => ({
            label: toTitleCase(key),
            value: formatFindingValue(value),
          }));

        return { summary, entries, paragraphs: [] as string[] };
      }
    } catch {
      // Fall back to plain-text formatting.
    }
  }

  const lines = trimmed
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean);

  return {
    summary: lines[0] ?? "",
    entries: [] as FindingEntry[],
    paragraphs: lines.slice(1),
  };
}

function MetaItem({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <div className="rounded-[20px] border border-white/8 bg-black/12 p-4">
      <p className="text-[10px] uppercase tracking-[0.18em] text-mist/45">{label}</p>
      <p className={cn("mt-2 text-sm font-medium text-sand", accent)}>{value}</p>
    </div>
  );
}

export function AICallLog({ strategy, executionMessage }: AICallLogProps) {
  const findings = extractFindings(strategy.ai_last_reasoning);
  const lastStatus = strategy.ai_last_decision_status ?? "No recent call";
  const lastProvider = strategy.ai_last_provider || strategy.ai_provider || "--";
  const lastModel = strategy.ai_last_model || strategy.ai_model || "--";

  return (
    <section className="panel grid gap-4 p-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-gold/80">AI Call Log</p>
          <h3 className="mt-2 text-xl font-semibold text-sand">Latest Inference</h3>
        </div>
        <p className="text-xs text-mist/45">Last updated {formatDateTime(strategy.ai_last_decision_at)}</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetaItem label="Status" value={lastStatus} accent={toneForStatus(strategy.ai_last_decision_status)} />
        <MetaItem label="Provider" value={lastProvider} />
        <MetaItem label="Model" value={lastModel} />
        <MetaItem label="Cooldown" value={`${formatNumber(strategy.ai_cooldown_seconds, 0)}s`} />
        <MetaItem label="Prompt Tokens" value={formatNumber(strategy.ai_last_prompt_tokens, 0)} />
        <MetaItem label="Completion Tokens" value={formatNumber(strategy.ai_last_completion_tokens, 0)} />
        <MetaItem label="Total Tokens" value={formatNumber(strategy.ai_last_total_tokens, 0)} />
        <MetaItem label="Last Cost" value={formatCurrency(strategy.ai_last_cost_usdt)} accent="text-gold" />
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <MetaItem label="Total Calls" value={formatNumber(strategy.ai_total_calls, 0)} />
        <MetaItem label="Total Tokens" value={formatNumber(strategy.ai_total_tokens, 0)} />
        <MetaItem label="Total Cost" value={formatCurrency(strategy.ai_total_cost_usdt)} accent="text-gold" />
      </div>

      {executionMessage ? (
        <div className="rounded-[20px] border border-gold/20 bg-gold/5 p-4">
          <p className="text-[10px] uppercase tracking-[0.18em] text-gold/70">Latest API Response</p>
          <p className="mt-2 break-words text-sm leading-6 text-sand">{executionMessage}</p>
        </div>
      ) : null}

      <div className="rounded-[24px] border border-white/8 bg-white/5 p-5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-mist/50">Last Findings</p>
            <h4 className="mt-2 text-lg font-semibold text-sand">API / AI Summary</h4>
          </div>
          <p className="text-xs text-mist/40">Formatted from `ai_last_reasoning`</p>
        </div>

        {findings.summary ? (
          <p className="mt-4 break-words text-sm leading-7 text-sand">{findings.summary}</p>
        ) : (
          <p className="mt-4 text-sm text-mist/55">No findings recorded yet.</p>
        )}

        {findings.entries.length ? (
          <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {findings.entries.map((entry) => (
              <div key={entry.label} className="rounded-[18px] border border-white/8 bg-black/10 p-4">
                <p className="text-[10px] uppercase tracking-[0.18em] text-mist/45">{entry.label}</p>
                <p className="mt-2 text-sm font-medium text-sand">{entry.value}</p>
              </div>
            ))}
          </div>
        ) : null}

        {findings.paragraphs.length ? (
          <div className="mt-4 space-y-3">
            {findings.paragraphs.map((paragraph, index) => (
              <p key={`${paragraph}-${index}`} className="text-sm leading-7 text-mist/72">
                {paragraph.replace(/^[-*]\s*/, "")}
              </p>
            ))}
          </div>
        ) : null}
      </div>
    </section>
  );
}
