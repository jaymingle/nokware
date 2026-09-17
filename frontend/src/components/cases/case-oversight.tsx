"use client";

import { useState } from "react";

import { CaseWorkspace } from "@/components/cases/case-workspace";
import { ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { useCaseOversight } from "@/lib/api/queries";
import { cn } from "@/lib/utils";

import type { CaseOversight, CaseSummary } from "@/lib/api/types";

const FILTERS = {
  all: { label: "All", matches: () => true },
  open: { label: "Open", matches: (c: CaseSummary) => c.status !== "resolved" && c.status !== "escalated" },
  escalated: { label: "Escalated", matches: (c: CaseSummary) => c.status === "escalated" },
  resolved: { label: "Resolved", matches: (c: CaseSummary) => c.status === "resolved" },
} as const;
type FilterKey = keyof typeof FILTERS;

function Stats({ stats }: { stats: CaseOversight["stats"] }) {
  const cards = [
    { label: "Open cases", value: String(stats.open), note: "everyday and public-safety reports", testId: "stat-open" },
    { label: "Escalated", value: String(stats.escalated), note: "waiting for your decision", testId: "stat-escalated" },
    { label: "Resolved", value: String(stats.resolved_30_days), note: "in the last 30 days", testId: "stat-resolved" },
    {
      label: "Personal safety, open",
      value: stats.personal_safety_open === null ? "Fewer than 5" : String(stats.personal_safety_open),
      note: "metro-wide only; never broken down",
      testId: "stat-safety",
    },
  ];
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <div key={card.label} className="rounded-xl border bg-card p-5" data-testid={card.testId}>
          <p className="text-[12.5px] text-ink-soft">{card.label}</p>
          <p className={cn("mt-2.5 font-heading leading-none tabular-nums", card.value.length > 4 ? "text-[26px]" : "text-[42px]")}>{card.value}</p>
          <p className="mt-1.5 text-[12px] text-ink-soft">{card.note}</p>
        </div>
      ))}
    </div>
  );
}

function Filters({ data, recipient, onRecipient, filter, onFilter }: {
  data: CaseOversight; recipient: string; onRecipient: (id: string) => void; filter: FilterKey; onFilter: (f: FilterKey) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <NativeSelect value={recipient} onChange={(e) => onRecipient(e.target.value)} aria-label="Department or agency" size="sm" data-testid="oversight-recipient-filter">
        <NativeSelectOption value="">All departments and agencies</NativeSelectOption>
        {data.recipients.map((r) => (
          <NativeSelectOption key={r.id} value={r.name}>{r.name}</NativeSelectOption>
        ))}
      </NativeSelect>
      {(Object.keys(FILTERS) as FilterKey[]).map((key) => (
        <button
          key={key}
          type="button"
          aria-pressed={filter === key}
          onClick={() => onFilter(key)}
          className={cn("rounded-lg border px-3 py-1.5 text-[12.5px] transition-colors", filter === key ? "border-teal bg-teal-tint font-medium text-teal" : "bg-card text-ink hover:border-teal")}
          data-testid={`oversight-filter-${key}`}
        >
          {FILTERS[key].label}
        </button>
      ))}
    </div>
  );
}

export function CaseOversightScreen() {
  const { data, error, isPending, refetch } = useCaseOversight();
  const [recipient, setRecipient] = useState("");
  const [filter, setFilter] = useState<FilterKey>("all");
  if (isPending) return <LoadingPanel label="Loading every case…" />;
  if (error) return <ErrorPanel message={error.message} onRetry={() => void refetch()} />;
  const shown = data.cases.filter((c) => FILTERS[filter].matches(c) && (!recipient || c.recipients.includes(recipient)));
  return (
    <div className="flex flex-col gap-6">
      <Stats stats={data.stats} />
      <CaseWorkspace
        title="Cases"
        cases={shown}
        empty="No cases match."
        recipients={data.recipients}
        toolbar={<Filters data={data} recipient={recipient} onRecipient={setRecipient} filter={filter} onFilter={setFilter} />}
      />
    </div>
  );
}
