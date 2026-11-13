import type { Metadata } from "next";
import type { ReactNode } from "react";
import AppShell from "@/components/AppShell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Primary Markets Deal Copilot",
  description: "Synthetic-data demo: deal workflow, order book, allocation, term sheets and an AI copilot",
};

// Runs before the page paints, so a saved dark theme does not flash white first.
const THEME_SCRIPT = `try{var t=localStorage.getItem("dc-theme");if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t)}catch(e){}`;

/** The outer HTML shell of every page. */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        {/* Inline on purpose: it must run before first paint to avoid a white flash in dark mode. */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body>
        {/* AppShell adds the top bar and session check, except on the login page. */}
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
