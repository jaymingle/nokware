import type { ReactNode } from "react";

import { RoleGate } from "@/components/portal/role-gate";

export default function MceLayout({ children }: { children: ReactNode }) {
  return <RoleGate role="mce">{children}</RoleGate>;
}
