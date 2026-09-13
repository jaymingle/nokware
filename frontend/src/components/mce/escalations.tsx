"use client";

import { useState } from "react";

import { ClockSummary } from "@/components/documents/clock-summary";
import { EmptyPanel, ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { EscalationCard } from "@/components/mce/escalation-card";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { useNow } from "@/hooks/use-now";
import { useDepartments, useEscalations } from "@/lib/api/queries";
import { splitByClock } from "@/lib/documents";

import type { DocumentOut } from "@/lib/api/types";

const ALL = "all";

type FilterProps = { value: string; onChange: (value: string) => void; documents: DocumentOut[] };

/** Every department, with how many of its disputes are waiting on the MCE. */
function DepartmentFilter({ value, onChange, documents }: FilterProps) {
  const { data: departments } = useDepartments();
  const waiting = (id: string) => documents.filter((doc) => doc.department === id).length;
  return (
    <div className="flex flex-col gap-1.5 sm:w-64">
      <Label htmlFor="department-filter">Department</Label>
      <NativeSelect
        id="department-filter"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full"
        data-testid="escalations-department-filter"
      >
        <NativeSelectOption value={ALL}>All departments</NativeSelectOption>
        {departments?.map((department) => (
          <NativeSelectOption key={department.id} value={department.id}>
            {waiting(department.id) > 0 ? `${department.name} · ${waiting(department.id)}` : department.name}
          </NativeSelectOption>
        ))}
      </NativeSelect>
    </div>
  );
}

function CardList({ label, documents }: { label: string; documents: DocumentOut[] }) {
  if (documents.length === 0) return null;
  return (
    <section aria-label={label} className="flex flex-col gap-4">
      {documents.map((doc) => (
        <EscalationCard key={doc.id} doc={doc} />
      ))}
    </section>
  );
}

function FilteredList({ documents, department, now }: { documents: DocumentOut[]; department: string; now: number }) {
  const shown = department === ALL ? documents : documents.filter((doc) => doc.department === department);
  if (shown.length === 0) {
    return <EmptyPanel title="Nothing escalated from this department">Choose another department, or all of them.</EmptyPanel>;
  }
  const { open, closed } = splitByClock(shown, now);
  return (
    <>
      <CardList label="Awaiting your ruling" documents={open} />
      <CardList label="Being published automatically" documents={closed} />
    </>
  );
}

export function Escalations() {
  const now = useNow();
  const [department, setDepartment] = useState(ALL);
  const { data, error, isPending, refetch } = useEscalations();
  if (isPending) return <LoadingPanel label="Loading escalated disputes…" />;
  if (error) return <ErrorPanel message={error.message} onRetry={() => void refetch()} />;
  if (data.length === 0) {
    return (
      <EmptyPanel title="No disputes waiting for your ruling">
        When a contributor escalates a department&apos;s dispute, it appears here with the time left before it publishes
        automatically.
      </EmptyPanel>
    );
  }
  const { open, closed } = splitByClock(data, now);
  return (
    <div className="flex flex-col gap-6">
      <ClockSummary
        open={open}
        closed={closed.length}
        now={now}
        unless={{ one: "you uphold the dispute", many: "you uphold the disputes" }}
        consequence="If you don't rule, each goes into the public Ledger and Ask when its clock runs out, as the contributor asked."
        testId="escalations-summary"
      />
      <DepartmentFilter value={department} onChange={setDepartment} documents={data} />
      <FilteredList documents={data} department={department} now={now} />
    </div>
  );
}
