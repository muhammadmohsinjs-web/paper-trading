import Link from "next/link";

import { cn } from "@/lib/format";

type ShellProps = {
  title: string;
  eyebrow?: string;
  description?: string;
  children: React.ReactNode;
};

const navItems = [
  { href: "/", label: "Overview" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/compare", label: "Compare" }
];

export function Shell({ title, eyebrow, description, children }: ShellProps) {
  return (
    <div className="min-h-screen bg-ink text-sand">
      <div className="mx-auto max-w-7xl px-4 pb-16 pt-6 sm:px-6 lg:px-8">
        <header className="mb-8 rounded-[32px] border border-white/10 bg-grain px-6 py-6 shadow-bloom sm:px-8">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="space-y-3">
              {eyebrow ? (
                <div className="text-xs uppercase tracking-[0.3em] text-mist/70">{eyebrow}</div>
              ) : null}
              <div>
                <h1 className="max-w-3xl text-4xl font-semibold tracking-tight text-sand sm:text-5xl">
                  {title}
                </h1>
                {description ? (
                  <p className="mt-3 max-w-2xl text-sm leading-6 text-mist/80 sm:text-base">
                    {description}
                  </p>
                ) : null}
              </div>
            </div>
            <nav className="flex flex-wrap gap-2">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "rounded-full border border-white/10 px-4 py-2 text-sm text-mist transition hover:border-rise/40 hover:bg-white/5 hover:text-sand"
                  )}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
        </header>
        <main>{children}</main>
      </div>
    </div>
  );
}
