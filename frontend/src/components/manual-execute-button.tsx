"use client";

import { useState, useTransition } from "react";

import { executeStrategy } from "@/lib/api";

type ManualExecuteButtonProps = {
  strategyId: string;
};

export function ManualExecuteButton({ strategyId }: ManualExecuteButtonProps) {
  const [result, setResult] = useState<string>("");
  const [isPending, startTransition] = useTransition();

  return (
    <div className="rounded-[24px] border border-white/10 bg-panel/80 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-[0.22em] text-mist/55">Manual Trigger</div>
          <div className="mt-2 text-xl font-semibold text-sand">Execute one decision cycle</div>
        </div>
        <button
          type="button"
          onClick={() =>
            startTransition(async () => {
              try {
                const response = await executeStrategy(strategyId);
                setResult(JSON.stringify(response, null, 2));
              } catch (error) {
                setResult(error instanceof Error ? error.message : "Execution failed");
              }
            })
          }
          className="rounded-full bg-rise px-5 py-2 text-sm font-semibold text-ink transition hover:opacity-90 disabled:opacity-50"
          disabled={isPending}
        >
          {isPending ? "Running..." : "Execute"}
        </button>
      </div>
      <pre className="mt-4 overflow-x-auto rounded-[18px] border border-white/8 bg-black/20 p-4 text-xs text-mist/70">
        {result || "No manual execution triggered yet."}
      </pre>
    </div>
  );
}
