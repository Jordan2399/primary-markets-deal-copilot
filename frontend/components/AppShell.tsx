"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import Nav from "@/components/Nav";
import { SessionProvider } from "@/lib/session";

/** Wraps every page: top bar, content area and footer. The login page is shown without them. */
export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  // The login page has its own layout and must work without a session.
  if (pathname.startsWith("/login")) return <>{children}</>;
  // SessionProvider holds back the pages until the server confirms who is signed in.
  return (
    <SessionProvider>
      <Nav />
      <div className="page">{children}</div>
      <footer className="footer">
        <span>Primary Markets Deal Copilot</span>
        <span>Synthetic data. Portfolio demo, not a bank system.</span>
      </footer>
    </SessionProvider>
  );
}
