import type { Metadata } from "next";
import { WorkspaceShell } from "@/components/workspace-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Paper Trading Dashboard",
  description: "Real-time crypto paper trading dashboard and AI strategy monitor."
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <WorkspaceShell>
          {children}
        </WorkspaceShell>
      </body>
    </html>
  );
}
