import { RoleGate } from "@/components/portal/role-gate";

import type { ReactNode } from "react";

export default function AgencyLayout({ children }: { children: ReactNode }) {
  return <RoleGate role="agency">{children}</RoleGate>;
}
