"use client";

import { usePathname } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { EnvironmentStrip } from "@/components/AdminNote";
import Nav from "@/components/Nav";
import { ToastProvider } from "@/components/Toast";
import { titleFor } from "@/lib/page-title";
import { SessionProvider } from "@/lib/session";

/** Keeps the browser tab title in step with the page ("Order book · Deal Copilot"). */
function TitleSync() {
  const pathname = usePathname();
  useEffect(() => {
    document.title = titleFor(pathname);
  }, [pathname]);
  return null;
}

/** Wraps every page: top bar, content area and footer. The login page is shown without them. */
export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  // The login page has its own layout and must work without a session.
  if (pathname.startsWith("/login")) return <>{children}</>;
  // SessionProvider holds back the pages until the server confirms who is signed in.
  return (
    <SessionProvider>
      {/* ToastProvider lets any page show a short confirmation ("Task updated"). */}
      <ToastProvider>
        <TitleSync />
        {/* Keyboard users can jump past the menu straight to the content. */}
        <a className="skip-link" href="#content">Skip to content</a>
        <Nav />
        <EnvironmentStrip />
        <div className="page" id="content" tabIndex={-1}>{children}</div>
        <footer className="footer">
          <span>Primary Markets Deal Copilot</span>
          <span>Secure session. Every change and every AI answer is recorded in the audit trail.</span>
        </footer>
      </ToastProvider>
    </SessionProvider>
  );
}
