"use client";

import { useState, type ReactNode } from "react";

import { CaseDetailPanel } from "@/components/cases/case-detail-panel";
import { CaseTable } from "@/components/cases/case-table";
import { Card } from "@/components/ui/card";

import type { CaseSummary, Option } from "@/lib/api/types";

type CaseWorkspaceProps = {
  title: string;
  cases: CaseSummary[];
  empty: ReactNode;
  toolbar?: ReactNode;
  recipients?: Option[];  // given for the MCE: turns on reassignment and the "With" line
};

export function CaseWorkspace({ title, cases, empty, toolbar, recipients }: CaseWorkspaceProps) {
  const [selected, setSelected] = useState<string | null>(null);
  function select(caseId: string) {
    setSelected(caseId);
    if (window.matchMedia("(max-width: 1023px)").matches) {
      requestAnimationFrame(() => document.getElementById("case-panel")?.scrollIntoView({ block: "start" }));
    }
  }
  return (
    <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(320px,400px)]">
      <Card className="gap-0 overflow-hidden py-0">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4">
          <h2 className="text-[19px]">{title}</h2>
          {toolbar}
        </div>
        {cases.length > 0 ? (
          <CaseTable cases={cases} selected={selected} onSelect={select} showRecipients={Boolean(recipients)} />
        ) : (
          <div className="px-5 py-6 text-[14px] text-ink-soft">{empty}</div>
        )}
      </Card>
      <aside id="case-panel" aria-label="Selected case" className="scroll-mt-6 rounded-xl border bg-card p-5 lg:sticky lg:top-6">
        <CaseDetailPanel caseId={selected} recipients={recipients} />
      </aside>
    </div>
  );
}
