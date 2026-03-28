"use client";

import { buttonClassName, Surface } from "@/components/ui";

export default function Error({
  error,
  reset
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <Surface className="max-w-xl border-red-200 bg-white p-6">
        <div className="text-[11px] font-medium uppercase tracking-[0.12em] text-red-700">Frontend error</div>
        <h1 className="mt-3 text-3xl font-semibold text-slate-900">Dashboard failed to load</h1>
        <p className="mt-3 text-sm text-slate-600">{error.message}</p>
        <button
          type="button"
          onClick={reset}
          className={`mt-5 ${buttonClassName("danger", "md")}`}
        >
          Retry
        </button>
      </Surface>
    </div>
  );
}
