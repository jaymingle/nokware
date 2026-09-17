"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useMe } from "@/lib/auth/auth-context";
import { ROLE_HOME } from "@/lib/portal/navigation";

import type { Role } from "@/lib/api/types";

/** Renders a role's pages only for that role; anyone else is sent to their own home. */
export function RoleGate({ role, children }: { role: Role; children: ReactNode }) {
  const me = useMe();
  const router = useRouter();
  const allowed = me.role === role;
  useEffect(() => {
    if (!allowed) router.replace(ROLE_HOME[me.role]);
  }, [allowed, me.role, router]);
  return allowed ? children : null;
}

/** /portal itself: send the user to their role's home. */
export function RoleRedirect() {
  const me = useMe();
  const router = useRouter();
  useEffect(() => {
    router.replace(ROLE_HOME[me.role]);
  }, [me.role, router]);
  return null;
}
