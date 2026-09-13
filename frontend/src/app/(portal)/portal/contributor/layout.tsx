import type { ReactNode } from "react";

import { RoleGate } from "@/components/portal/role-gate";

export default function ContributorLayout({ children }: { children: ReactNode }) {
  return <RoleGate role="contributor">{children}</RoleGate>;
}
