import { RoleGate } from "@/components/portal/role-gate";

import type { ReactNode } from "react";

export default function MceLayout({ children }: { children: ReactNode }) {
  return <RoleGate role="mce">{children}</RoleGate>;
}
