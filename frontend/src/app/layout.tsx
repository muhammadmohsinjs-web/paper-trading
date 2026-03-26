import type { Metadata } from "next";
import Link from "next/link";
import { backendBaseUrl } from "@/lib/env";
import "./globals.css";

export const metadata: Metadata = {
  title: "Paper Trading Dashboard",
  description: "Real-time crypto paper trading dashboard and AI strategy monitor."
};

const nav = [
  { href: "/", label: "Dashboard" },
  { href: "/leaderboard", label: "Leaderboard" },
  { href: "/compare", label: "Compare" },
  { href: "/logs", label: "AI Logs" }
];

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <div className="app-shell">
          <aside className="app-rail">
            <div className="app-rail-header">
              <div className="app-mark">Paper Trading</div>

              <div className="app-brand">
                <h1>Portfolio Control Room</h1>
                <p>
                  Shared-wallet multicoin execution, daily watchlists, AI oversight, and operator-grade
                  portfolio context.
                </p>
              </div>

              <div className="app-rail-card">
                <span>Operating Mode</span>
                <strong>Multicoin Shared Wallet</strong>
                <p>Designed around portfolio orchestration rather than exchange-style tape watching.</p>
              </div>

              <nav className="app-nav">
                {nav.map((item) => (
                  <Link key={item.href} href={item.href} className="app-nav-link">
                    <span>{item.label}</span>
                  </Link>
                ))}
                <a
                  href={`${backendBaseUrl}/docs`}
                  target="_blank"
                  rel="noreferrer"
                  className="app-nav-external"
                >
                  <span>Backend Docs</span>
                </a>
              </nav>
            </div>

            <div className="app-rail-footer">
              <div className="app-rail-card">
                <span>Design Intent</span>
                <strong>Control Desk, Not Exchange</strong>
                <p>
                  The interface favors watchlists, wallet exposure, execution context, and strategy health over
                  noisy market chrome.
                </p>
              </div>

              <p className="app-note">
                Future modules can plug into the same shell: scanner outputs, portfolio rules, AI audits, and
                symbol-level workspaces.
              </p>
            </div>
          </aside>

          <main className="app-main">
            <div className="app-topbar">
              <div className="app-topbar-meta">
                <span>Strategy Oversight</span>
                <span>Daily top picks, shared-wallet exposure, and execution telemetry in one workspace.</span>
              </div>
              <div className="app-topbar-badge">Liquid-20 universe</div>
            </div>

            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
