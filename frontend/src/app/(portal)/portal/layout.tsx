import type { ReactNode } from "react";
import type { Metadata } from "next";

import { PortalShell } from "@/components/portal/portal-shell";

export const metadata: Metadata = { title: "Portal" };

export default function PortalLayout({ children }: { children: ReactNode }) {
  return <PortalShell>{children}</PortalShell>;
}
