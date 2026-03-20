"use client";

import type { OpenAIUsageResponse } from "@/lib/types";

type Props = {
  data: OpenAIUsageResponse;
};

export function OpenAIUsagePanel({ data }: Props) {
  if (!data.configured) {
    return (
      <div className="panel border border-amber-400/20 p-4">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 text-amber-400">!</span>
          <div>
            <p className="text-sm font-medium text-sand">OpenAI Usage API not configured</p>
            <p className="mt-1 text-xs text-mist/60">
              Set <code className="rounded bg-white/5 px-1.5 py-0.5">OPENAI_ADMIN_KEY</code> in your .env to fetch real usage data directly from OpenAI.
              Create one at{" "}
              <span className="text-gold">platform.openai.com/settings/organization/admin-keys</span>
            </p>
          </div>
        </div>
      </div>
    );
  }

  const hasErrors = data.costs_error || data.usage_error;

  return (
    <div className="panel overflow-hidden">
      <div className="border-b border-white/10 px-4 py-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.28em] text-green-400">OpenAI Live Usage</p>
            <p className="mt-1 text-xs text-mist/50">
              Last {data.days} days — fetched from OpenAI
              {data.filtered ? " (filtered to this API key)" : ""}
            </p>
          </div>
          {data.costs && (
            <div className="text-right">
              <p className="text-2xl font-semibold text-gold">${data.costs.total_usd.toFixed(4)}</p>
              <p className="text-xs text-mist/50">Actual billed cost</p>
            </div>
          )}
        </div>
      </div>

      {hasErrors && (
        <div className="border-b border-red-400/20 bg-red-400/5 px-4 py-2 text-xs text-red-400">
          {data.costs_error && <p>Costs API: {data.costs_error}</p>}
          {data.usage_error && <p>Usage API: {data.usage_error}</p>}
        </div>
      )}

      {data.usage && (
        <div className="p-4">
          <div className="mb-4 grid grid-cols-3 gap-4">
            <div>
              <p className="text-lg font-semibold text-sand">{data.usage.total_requests.toLocaleString()}</p>
              <p className="text-xs text-mist/50">API Requests</p>
            </div>
            <div>
              <p className="text-lg font-semibold text-sand">{data.usage.total_input_tokens.toLocaleString()}</p>
              <p className="text-xs text-mist/50">Input Tokens</p>
            </div>
            <div>
              <p className="text-lg font-semibold text-sand">{data.usage.total_output_tokens.toLocaleString()}</p>
              <p className="text-xs text-mist/50">Output Tokens</p>
            </div>
          </div>

          {/* Per-model breakdown */}
          {Object.keys(data.usage.by_model).length > 0 && (
            <div>
              <p className="mb-2 text-xs uppercase text-mist/40">By Model</p>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-left text-xs text-mist/50">
                      <th className="pb-2 pr-4">Model</th>
                      <th className="pb-2 pr-4 text-right">Requests</th>
                      <th className="pb-2 pr-4 text-right">Input Tokens</th>
                      <th className="pb-2 text-right">Output Tokens</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(data.usage.by_model)
                      .sort(([, a], [, b]) => b.requests - a.requests)
                      .map(([model, usage]) => (
                        <tr key={model} className="border-b border-white/5">
                          <td className="py-2 pr-4 text-sand">{model}</td>
                          <td className="py-2 pr-4 text-right tabular-nums text-mist/60">{usage.requests.toLocaleString()}</td>
                          <td className="py-2 pr-4 text-right tabular-nums text-mist/60">{usage.input_tokens.toLocaleString()}</td>
                          <td className="py-2 text-right tabular-nums text-mist/60">{usage.output_tokens.toLocaleString()}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Daily cost chart (simple bar representation) */}
      {data.costs?.daily && data.costs.daily.length > 0 && (
        <div className="border-t border-white/10 p-4">
          <p className="mb-2 text-xs uppercase text-mist/40">Daily Cost</p>
          <div className="flex items-end gap-1" style={{ height: 64 }}>
            {(() => {
              const maxCost = Math.max(...data.costs!.daily.map((d) => d.cost_usd), 0.001);
              return data.costs!.daily.map((d) => (
                <div key={d.date} className="group relative flex-1" title={`${d.date}: $${d.cost_usd.toFixed(4)}`}>
                  <div
                    className="w-full rounded-t bg-gold/60 transition hover:bg-gold"
                    style={{ height: `${Math.max((d.cost_usd / maxCost) * 100, 2)}%` }}
                  />
                </div>
              ));
            })()}
          </div>
          <div className="mt-1 flex justify-between text-[10px] text-mist/30">
            <span>{data.costs.daily[0]?.date}</span>
            <span>{data.costs.daily[data.costs.daily.length - 1]?.date}</span>
          </div>
        </div>
      )}
    </div>
  );
}
