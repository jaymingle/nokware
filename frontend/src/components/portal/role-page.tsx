"use client";

import { PageShell } from "@/components/page-shell";
import { Card, CardContent } from "@/components/ui/card";
import { useMe } from "@/lib/auth/auth-context";
import { roleLabel } from "@/lib/portal/navigation";

import type { ReactNode } from "react";

type RolePageProps = {
  title: string;
  lead?: ReactNode;
  /** Replaces the default eyebrow, where the user sits (e.g. "Finance"). */
  eyebrow?: string;
  children?: ReactNode;
};

/** Every portal page is a page like any other, at the width its queues and tables need. */
export function RolePage({ title, lead, eyebrow, children }: RolePageProps) {
  const me = useMe();
  return (
    <PageShell width="data" eyebrow={eyebrow ?? roleLabel(me)} title={title} lead={lead}>
      {children ?? (
        <Card>
          <CardContent className="text-sm text-ink-soft">This view is built in the next step.</CardContent>
        </Card>
      )}
    </PageShell>
  );
}
