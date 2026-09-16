"use client";

import { CircleCheckIcon, CircleDashedIcon, CircleXIcon, MinusIcon, type LucideIcon } from "lucide-react";
import { useState } from "react";

import { RecordDetail } from "@/components/accountability/record-detail";
import { ReportingGaps } from "@/components/accountability/reporting-gaps";
import { ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { PageIntro } from "@/components/portal/page-intro";
import { usePublishingRecord } from "@/lib/api/public-queries";
import { ASSUMPTION_NOTE, LEDGER_YEAR_NOTE, STATE_LABELS, dateLabel, periodsIn, planSpan, yearFromLedger, yearsOf, type RecordState } from "@/lib/accountability";
import { cn } from "@/lib/utils";

import type { PublishingRecord, RecordPeriod, RecordRequirement } from "@/lib/api/types";

const MARKS: Record<RecordState, { icon: LucideIcon; className: string }> = {
  held: { icon: CircleCheckIcon, className: "text-teal" },
  related: { icon: CircleDashedIcon, className: "text-gold" },
  missing: { icon: CircleXIcon, className: "text-brick" },
  not_due: { icon: MinusIcon, className: "text-ink-muted" },
};

type Selected = { requirement: string; period: string } | null;
type Select = (requirement: RecordRequirement, period: RecordPeriod) => void;

function Mark({ state, small = false }: { state: RecordState; small?: boolean }) {
  const { icon: Icon, className } = MARKS[state];
  return <Icon aria-hidden className={cn(small ? "size-4" : "size-5", className)} />;
}

function Cell({ requirement, period, selected, onSelect, short }: {
  requirement: RecordRequirement; period: RecordPeriod; selected: boolean; onSelect: Select; short?: string;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(requirement, period)}
      aria-pressed={selected}
      aria-label={`${requirement.name}, ${period.label}: ${STATE_LABELS[period.state]}${yearFromLedger(period) ? ` (${LEDGER_YEAR_NOTE})` : ""}`}
      className={cn("inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[11.5px] text-ink-soft hover:bg-paper-subtle", selected && "bg-teal-tint ring-1 ring-teal")}
      data-testid={`record-${requirement.id}-${period.label.replace(/\W+/g, "-")}`}
    >
      <Mark state={period.state} small={Boolean(short)} />
      {short}
      {yearFromLedger(period) ? <sup aria-hidden>†</sup> : null}
    </button>
  );
}

function PlanCells({ requirement, years, isSelected, onSelect }: { requirement: RecordRequirement; years: number[]; isSelected: (p: RecordPeriod) => boolean; onSelect: Select }) {
  const cells = [];
  for (let i = 0; i < years.length; ) {
    const period = periodsIn(requirement, years[i])[0];
    const span = period ? planSpan(period, years.slice(i)) : 1;
    cells.push(
      <td key={years[i]} colSpan={span} className="border-l px-2 py-2 text-center">
        {period ? <span className="inline-flex items-center gap-2"><Cell requirement={requirement} period={period} selected={isSelected(period)} onSelect={onSelect} /><span className="text-[11.5px] text-ink-soft">{period.label}</span></span> : null}
      </td>,
    );
    i += span;
  }
  return <>{cells}</>;
}

function Row({ requirement, years, selected, onSelect }: { requirement: RecordRequirement; years: number[]; selected: Selected; onSelect: Select }) {
  const isSelected = (p: RecordPeriod) => selected?.requirement === requirement.id && selected.period === p.label;
  return (
    <tr className="border-t align-middle">
      <th scope="row" className="px-3 py-2.5 text-left font-normal">
        <div className="text-[14px] font-medium">{requirement.name}</div>
        {requirement.issued_by ? <div className="text-[12px] text-ink-soft">Issued by {requirement.issued_by}</div> : null}
        {requirement.expected_note ? <div className="text-[11.5px] text-ink-muted">{requirement.expected_note}</div> : null}
      </th>
      {requirement.cadence === "as_issued" ? (
        <td colSpan={years.length} className="border-l px-3 py-2.5 text-[13px] text-ink-soft" data-testid={`record-${requirement.id}-as-issued`}>
          Issued on no fixed schedule, so no year is marked missing. {requirement.held.length ? `The Ledger holds ${requirement.held.length}.` : "The Ledger holds none."}
        </td>
      ) : requirement.cadence === "plan_period" ? (
        <PlanCells requirement={requirement} years={years} isSelected={isSelected} onSelect={onSelect} />
      ) : (
        years.map((year) => (
          <td key={year} className="border-l px-1.5 py-2 text-center">
            <div className="flex flex-wrap justify-center gap-0.5">
              {periodsIn(requirement, year).map((period) => (
                <Cell key={period.label} requirement={requirement} period={period} selected={isSelected(period)} onSelect={onSelect}
                  short={requirement.cadence === "quarterly" ? `Q${period.quarter}` : undefined} />
              ))}
            </div>
          </td>
        ))
      )}
    </tr>
  );
}

function Group({ record, index, selected, onSelect }: { record: PublishingRecord; index: number; selected: Selected; onSelect: Select }) {
  const group = record.groups[index];
  const years = yearsOf(record);
  const open = group.requirements.find((r) => r.id === selected?.requirement);
  const period = open?.periods.find((p) => p.label === selected?.period);
  return (
    <section aria-labelledby={`group-${group.id}`} className="flex flex-col gap-3" data-testid={`record-group-${group.id}`}>
      <h2 id={`group-${group.id}`} className="text-[21px]">{group.name}</h2>
      <div className="overflow-x-auto rounded-xl border bg-card">
        <table className="w-full min-w-[720px] border-collapse">
          <caption className="sr-only">{group.name}: each document by year, and whether The Ledger holds it</caption>
          <thead>
            <tr className="text-[12.5px] text-ink-soft">
              <th scope="col" className="w-[30%] px-3 py-2 text-left font-normal">Document</th>
              {years.map((year) => <th key={year} scope="col" className="border-l px-2 py-2 font-normal tabular-nums">{year}</th>)}
            </tr>
          </thead>
          <tbody>
            {group.requirements.map((r) => <Row key={r.id} requirement={r} years={years} selected={selected} onSelect={onSelect} />)}
          </tbody>
        </table>
      </div>
      {group.requirements.some((r) => r.periods.some(yearFromLedger)) ? (
        <p className="text-[12px] text-ink-soft" data-testid={`record-group-${group.id}-footnote`}>† {LEDGER_YEAR_NOTE}</p>
      ) : null}
      {open && period ? <RecordDetail requirement={open} period={period} checked={record.documents_centre_checked} /> : null}
    </section>
  );
}

function HowToRead({ record }: { record: PublishingRecord }) {
  return (
    <div className="flex flex-col gap-3 rounded-xl border bg-card p-4 text-[13.5px] sm:p-5" data-testid="record-how-to-read">
      <ul className="flex flex-wrap gap-x-5 gap-y-2">
        {(Object.keys(STATE_LABELS) as RecordState[]).map((state) => (
          <li key={state} className="flex items-center gap-1.5"><Mark state={state} />{STATE_LABELS[state]}</li>
        ))}
      </ul>
      <p>
        <strong className="font-medium">Not found</strong> means not found in{" "}
        <a href={record.documents_centre} target="_blank" rel="noopener noreferrer" className="text-teal underline-offset-2 hover:underline">ama.gov.gh&apos;s Documents Centre</a>{" "}
        (checked {dateLabel(record.documents_centre_checked)}) and not in The Ledger. It doesn&apos;t mean the document doesn&apos;t exist: it may simply not have been published online. <strong className="font-medium">Related documents only</strong> means The Ledger holds documents about the same thing, but not the document itself.
      </p>
      <p className="text-ink-soft">{ASSUMPTION_NOTE}</p>
      <p className="text-ink-soft">Choose any mark to see what The Ledger holds, including what it does hold from the same department that year, and how to request what&apos;s missing.</p>
    </div>
  );
}

function Summary({ record }: { record: PublishingRecord }) {
  const { due, held, related, missing } = record.summary;
  return (
    <p className="text-[15px]" data-testid="record-summary">
      Of the <strong className="font-medium tabular-nums">{due}</strong> documents we would expect by now since {record.first_year} (each quarter counted on its own), The Ledger holds{" "}
      <strong className="font-medium tabular-nums">{held}</strong>. For <strong className="font-medium tabular-nums">{related}</strong> it holds related documents only, and{" "}
      <strong className="font-medium tabular-nums">{missing}</strong> were not found.
    </p>
  );
}

/** What the Assembly is required to publish, against what The Ledger holds, by year. */
export function PublishingRecordPage() {
  const record = usePublishingRecord();
  const [selected, setSelected] = useState<Selected>(null);
  const onSelect: Select = (requirement, period) =>
    setSelected((current) => (current?.requirement === requirement.id && current.period === period.label ? null : { requirement: requirement.id, period: period.label }));
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-7">
      <PageIntro eyebrow="Accountability" title="What the Assembly publishes">
        The documents the Accra Metropolitan Assembly is required to publish, against what The Ledger holds, year by year. It shows the gaps, not just the contents.
      </PageIntro>
      {record.isPending ? <LoadingPanel label="Checking the record…" /> : null}
      {record.error ? <ErrorPanel message={record.error.message} onRetry={() => record.refetch()} /> : null}
      {record.data ? (
        <>
          <Summary record={record.data} />
          <ReportingGaps gaps={record.data.gaps} about={record.data.gaps_about} />
          <HowToRead record={record.data} />
          {record.data.groups.map((group, index) => <Group key={group.id} record={record.data} index={index} selected={selected} onSelect={onSelect} />)}
        </>
      ) : null}
    </div>
  );
}
