import type { ReactNode } from "react";

import { RoleGate } from "@/components/portal/role-gate";

export default function DepartmentLayout({ children }: { children: ReactNode }) {
  return <RoleGate role="department">{children}</RoleGate>;
}
