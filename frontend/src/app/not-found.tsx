import Link from "next/link";
import { buttonClassName, Surface } from "@/components/ui";

export default function NotFound() {
  return (
    <Surface className="mx-auto max-w-xl p-8 text-center">
      <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">Not Found</p>
      <h2 className="mt-3 text-3xl font-semibold text-slate-900">Strategy unavailable</h2>
      <p className="mt-3 text-sm text-slate-600">
        The requested route or strategy could not be loaded from the backend.
      </p>
      <Link
        href="/"
        className={`mt-6 ${buttonClassName("secondary", "md")}`}
      >
        Back to dashboard
      </Link>
    </Surface>
  );
}
