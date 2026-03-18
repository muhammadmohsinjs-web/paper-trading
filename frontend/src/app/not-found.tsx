import Link from "next/link";

export default function NotFound() {
  return (
    <div className="panel mx-auto max-w-xl p-8 text-center">
      <p className="text-xs uppercase tracking-[0.28em] text-gold">Not Found</p>
      <h2 className="mt-3 text-3xl font-semibold text-sand">Strategy unavailable</h2>
      <p className="mt-3 text-sm text-mist/65">
        The requested route or strategy could not be loaded from the backend.
      </p>
      <Link
        href="/"
        className="mt-6 inline-flex rounded-full border border-gold/40 px-4 py-2 text-sm text-gold transition hover:bg-gold/10"
      >
        Back to dashboard
      </Link>
    </div>
  );
}
