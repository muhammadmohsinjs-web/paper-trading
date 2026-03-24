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
        <div className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-4 pb-10 pt-6 sm:px-6 lg:px-8">
          <header className="panel mb-8 overflow-hidden shadow-bloom">
            <div className="flex flex-col gap-6 border-b border-white/10 bg-grain px-6 py-6 lg:flex-row lg:items-end lg:justify-between">
              <div className="space-y-3">
                <p className="text-xs uppercase tracking-[0.32em] text-gold">Paper Trading</p>
                <div>
                  <h1 className="text-3xl font-semibold tracking-tight text-sand sm:text-4xl">
                    Live Strategy Control Room
                  </h1>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-mist/70">
                    Real-time market context, strategy performance, and AI execution telemetry in one
                    dashboard.
                  </p>
                </div>
              </div>

              <nav className="flex flex-wrap gap-3">
                {nav.map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className="rounded-full border border-white/10 px-4 py-2 text-sm text-mist/85 transition hover:border-gold/50 hover:text-sand"
                  >
                    {item.label}
                  </Link>
                ))}
                <a
                  href={`${backendBaseUrl}/docs`}
                  target="_blank"
                  rel="noreferrer"
                  className="rounded-full border border-gold/40 bg-gold/10 px-4 py-2 text-sm text-gold transition hover:bg-gold/15"
                >
                  Backend Docs
                </a>
              </nav>
            </div>
          </header>

          <main className="flex-1">{children}</main>
        </div>
      </body>
    </html>
  );
}
