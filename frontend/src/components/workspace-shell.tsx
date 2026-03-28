"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo, useState } from "react";
import { backendBaseUrl } from "@/lib/env";
import { buttonClassName } from "@/components/ui";
import { cn } from "@/lib/format";

const nav = [
  { href: "/", label: "Overview", short: "OV" },
  { href: "/leaderboard", label: "Leaderboard", short: "LB" },
  { href: "/compare", label: "Compare", short: "CP" },
  { href: "/logs", label: "AI Logs", short: "AI" }
];

const routeMeta: Record<string, { title: string }> = {
  "/": { title: "Overview" },
  "/leaderboard": { title: "Leaderboard" },
  "/compare": { title: "Compare" },
  "/logs": { title: "AI Logs" }
};

type WorkspaceShellProps = {
  children: React.ReactNode;
};

export function WorkspaceShell({ children }: WorkspaceShellProps) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  const current = useMemo(() => {
    if (pathname.startsWith("/strategies/")) {
      return { title: "Strategy Detail" };
    }
    return routeMeta[pathname] ?? { title: "Workspace" };
  }, [pathname]);

  return (
    <div className="app-shell">
      <div
        aria-hidden="true"
        className={cn("app-overlay", mobileOpen && "app-overlay-open")}
        onClick={() => setMobileOpen(false)}
      />

      <aside className="app-rail" data-collapsed={collapsed} data-mobile-open={mobileOpen}>
        <div className="app-rail-header">
          <div className="flex items-center justify-between gap-3">
            <Link href="/" className="app-brandmark" onClick={() => setMobileOpen(false)}>
              <span className="app-brandmark-icon">PT</span>
              <div className={cn("min-w-0", collapsed && "lg:hidden")}>
                <p className="text-sm font-semibold text-slate-900">Paper Trading</p>
              </div>
            </Link>

            <button
              type="button"
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              onClick={() => setCollapsed((value) => !value)}
              className={cn(buttonClassName("tertiary", "sm"), "hidden lg:inline-flex")}
            >
              {collapsed ? "Expand" : "Collapse"}
            </button>
          </div>

          <nav className="app-nav">
            {nav.map((item) => {
              const active =
                item.href === "/"
                  ? pathname === item.href
                  : pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn("app-nav-link", active && "app-nav-link-active")}
                  title={collapsed ? item.label : undefined}
                  onClick={() => setMobileOpen(false)}
                >
                  <span className="app-nav-icon">{item.short}</span>
                  <span className={cn("min-w-0", collapsed && "lg:hidden")}>{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>
      </aside>

      <div className="app-main-wrap">
        <header className="app-topbar">
          <div className="flex items-center gap-3">
            <button
              type="button"
              aria-label="Open navigation"
              onClick={() => setMobileOpen(true)}
              className={cn(buttonClassName("secondary", "sm"), "lg:hidden")}
            >
              Menu
            </button>
            <p className="text-sm font-medium text-slate-900">{current.title}</p>
          </div>

          <a
            href={`${backendBaseUrl}/docs`}
            target="_blank"
            rel="noreferrer"
            className="text-sm text-slate-500 transition hover:text-slate-900"
          >
            Backend docs
          </a>
        </header>

        <main className="app-main">{children}</main>
      </div>
    </div>
  );
}
