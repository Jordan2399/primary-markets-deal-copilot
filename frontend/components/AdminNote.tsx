"use client";

import type { ReactNode } from "react";
import { useSession } from "@/lib/session";

/** Shows its children to administrators only. Everyone else sees nothing (and no gap). */
export function AdminOnly({ children }: { children: ReactNode }) {
  const { user } = useSession();
  return user.role === "admin" ? <>{children}</> : null;
}

/**
 * A slim strip under the top bar that tells the administrator this is a demonstration
 * environment. Other roles use the application without any such message.
 */
export function EnvironmentStrip() {
  return (
    <AdminOnly>
      <div className="env-strip" role="note">
        <strong>Demonstration environment</strong>
        <span>All deals, investors and orders are synthetic. Only administrators see this notice.</span>
      </div>
    </AdminOnly>
  );
}
