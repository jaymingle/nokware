import type { ReactNode } from "react";

import { RoleGate } from "@/components/portal/role-gate";

export default function AgencyLayout({ children }: { children: ReactNode }) {
  return <RoleGate role="agency">{children}</RoleGate>;
}
