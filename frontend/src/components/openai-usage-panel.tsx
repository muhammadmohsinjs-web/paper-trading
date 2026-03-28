"use client";

import type { OpenAIUsageResponse } from "@/lib/types";
import { MetricStrip } from "@/components/ui";

type Props = {
  data: OpenAIUsageResponse;
};

export function OpenAIUsagePanel({ data }: Props) {
  if (!data.configured) {
    return (
      <section className="space-y-2">
        <h2 className="text-lg font-semibold text-slate-900">OpenAI usage</h2>
        <p className="text-sm text-slate-600">
          Set <code className="rounded bg-white px-1.5 py-0.5">OPENAI_ADMIN_KEY</code> in your
          .env to fetch real usage data directly from OpenAI.
        </p>
      </section>
    );
  }

  const hasErrors = data.lookup_error || data.costs_error || data.usage_error;

  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-2 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold text-slate-900">OpenAI usage</h2>
          <p className="text-sm text-slate-600">
            Last {data.days} days fetched from OpenAI{data.filtered ? " for this API key" : ""}.
          </p>
        </div>
        {data.costs ? (
          <p className="text-sm text-slate-500">
            Billed cost <span className="font-semibold text-blue-700">${data.costs.total_usd.toFixed(4)}</span>
          </p>
        ) : null}
      </div>

      {hasErrors ? (
        <div className="space-y-1 text-xs text-red-700">
          {data.lookup_error ? <p>API key lookup: {data.lookup_error}</p> : null}
          {data.costs_error ? <p>Costs API: {data.costs_error}</p> : null}
          {data.usage_error ? <p>Usage API: {data.usage_error}</p> : null}
        </div>
      ) : null}

      {data.usage ? (
        <>
          <MetricStrip
            items={[
              { label: "API requests", value: data.usage.total_requests.toLocaleString() },
              { label: "Input tokens", value: data.usage.total_input_tokens.toLocaleString() },
              { label: "Output tokens", value: data.usage.total_output_tokens.toLocaleString() }
            ]}
          />

          {Object.keys(data.usage.by_model).length > 0 ? (
            <div className="space-y-3">
              <h3 className="text-sm font-semibold text-slate-900">By model</h3>
              <div className="table-shell overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Model</th>
                      <th className="text-right">Requests</th>
                      <th className="text-right">Input Tokens</th>
                      <th className="text-right">Output Tokens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(data.usage.by_model)
                      .sort(([, a], [, b]) => b.requests - a.requests)
                      .map(([model, usage]) => (
                        <tr key={model}>
                          <td className="font-medium text-slate-900">{model}</td>
                          <td className="text-right tabular-nums">{usage.requests.toLocaleString()}</td>
                          <td className="text-right tabular-nums">{usage.input_tokens.toLocaleString()}</td>
                          <td className="text-right tabular-nums">{usage.output_tokens.toLocaleString()}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : null}
        </>
      ) : null}

      {data.costs?.daily && data.costs.daily.length > 0 ? (
        <div className="space-y-2">
          <h3 className="text-sm font-semibold text-slate-900">Daily cost</h3>
          <div className="flex items-end gap-1" style={{ height: 64 }}>
            {(() => {
              const maxCost = Math.max(...data.costs!.daily.map((day) => day.cost_usd), 0.001);
              return data.costs!.daily.map((day) => (
                <div
                  key={day.date}
                  className="group relative flex-1"
                  title={`${day.date}: $${day.cost_usd.toFixed(4)}`}
                >
                  <div
                    className="w-full rounded-t bg-blue-200 transition hover:bg-blue-400"
                    style={{ height: `${Math.max((day.cost_usd / maxCost) * 100, 2)}%` }}
                  />
                </div>
              ));
            })()}
          </div>
          <div className="flex justify-between text-[10px] text-slate-500">
            <span>{data.costs.daily[0]?.date}</span>
            <span>{data.costs.daily[data.costs.daily.length - 1]?.date}</span>
          </div>
        </div>
      ) : null}
    </section>
  );
}
