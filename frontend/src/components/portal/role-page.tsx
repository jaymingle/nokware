"use client";

import type { ReactNode } from "react";

import { PageIntro } from "@/components/portal/page-intro";
import { Card, CardContent } from "@/components/ui/card";
import { useMe } from "@/lib/auth/auth-context";
import { roleLabel } from "@/lib/portal/navigation";

/** A portal page headed by where the user sits (e.g. "Finance") and the page's title. */
export function RolePage({ title, lead, children }: { title: string; lead?: ReactNode; children?: ReactNode }) {
  const me = useMe();
  return (
    <>
      <PageIntro eyebrow={roleLabel(me)} title={title}>
        {lead}
      </PageIntro>
      {children ?? (
        <Card>
          <CardContent className="text-sm text-ink-soft">This view is built in the next step.</CardContent>
        </Card>
      )}
    </>
  );
}
