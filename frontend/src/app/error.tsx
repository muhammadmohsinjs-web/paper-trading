"use client";

export default function Error({
  error,
  reset
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-ink px-4">
      <div className="max-w-xl rounded-[28px] border border-fall/30 bg-panel p-6 text-sand">
        <div className="text-xs uppercase tracking-[0.24em] text-fall">Frontend error</div>
        <h1 className="mt-3 text-3xl font-semibold">Dashboard failed to load</h1>
        <p className="mt-3 text-sm text-mist/70">{error.message}</p>
        <button
          type="button"
          onClick={reset}
          className="mt-5 rounded-full bg-fall px-4 py-2 text-sm font-semibold text-ink"
        >
          Retry
        </button>
      </div>
    </div>
  );
}
