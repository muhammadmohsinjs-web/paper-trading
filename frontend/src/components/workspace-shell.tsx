"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo, useState } from "react";
import { backendBaseUrl } from "@/lib/env";
import { buttonClassName } from "@/components/ui";
import { cn } from "@/lib/format";

const navIcons: Record<string, React.ReactNode> = {
  "/": (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><rect x="2" y="2" width="5.5" height="5.5" rx="1.5" stroke="currentColor" strokeWidth="1.4"/><rect x="10.5" y="2" width="5.5" height="5.5" rx="1.5" stroke="currentColor" strokeWidth="1.4"/><rect x="2" y="10.5" width="5.5" height="5.5" rx="1.5" stroke="currentColor" strokeWidth="1.4"/><rect x="10.5" y="10.5" width="5.5" height="5.5" rx="1.5" stroke="currentColor" strokeWidth="1.4"/></svg>
  ),
  "/leaderboard": (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M3 14V9h3v5H3Zm4.5 0V4H10v10H7.5Zm4.5 0V7h3v7h-3Z" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>
  ),
  "/compare": (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M6 3v12M12 3v12" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/><path d="M2 7h6M10 11h6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
  ),
  "/logs": (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M9 2a4.5 4.5 0 0 1 4.5 4.5c0 1.7-.9 3.2-2.3 4L11 16H7l-.2-5.5A4.5 4.5 0 0 1 9 2Z" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/><path d="M7 16h4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
  ),
  "/scan-audit": (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><circle cx="8" cy="8" r="5" stroke="currentColor" strokeWidth="1.4"/><path d="M12 12l4 4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
  ),
  "/review": (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M3 5h12M3 9h8M3 13h5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/><circle cx="14" cy="13" r="2.5" stroke="currentColor" strokeWidth="1.4"/><path d="M15.8 15.8l1.7 1.7" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>
  ),
};

const nav = [
  { href: "/", label: "Overview" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/compare", label: "Compare" },
  { href: "/logs", label: "AI Logs" },
  { href: "/scan-audit", label: "Scan Audit" },
  { href: "/review", label: "Review" },
];

const routeMeta: Record<string, { title: string }> = {
  "/": { title: "Overview" },
  "/leaderboard": { title: "Leaderboard" },
  "/compare": { title: "Compare" },
  "/logs": { title: "AI Logs" },
  "/scan-audit": { title: "Scan Audit" },
  "/review": { title: "Review" },
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
                <p className="text-[11px] text-slate-400 leading-tight">Sim engine v1.0</p>
              </div>
            </Link>

            <button
              type="button"
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              onClick={() => setCollapsed((value) => !value)}
              className="app-collapse-btn hidden lg:inline-flex"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                {collapsed ? (
                  <path d="M6 3l5 5-5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                ) : (
                  <path d="M10 3L5 8l5 5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                )}
              </svg>
            </button>
          </div>

          <div className="app-rail-divider" />

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
                  <span className="app-nav-icon">{navIcons[item.href]}</span>
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
