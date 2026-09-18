"use client";

import { Lines, type Line } from "@/components/accountability/figure-lines";
import { OtherView } from "@/components/accountability/other-view";
import { PetitionFigures } from "@/components/accountability/petition-figures";
import { CountValue } from "@/components/dashboard/count";
import { ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { PageIntro } from "@/components/portal/page-intro";
import { isActive } from "@/lib/accountability";
import { useResponsiveness } from "@/lib/api/public-queries";
import { formatDays } from "@/lib/report/dashboard";
import { formatDate } from "@/lib/time";

import type { DepartmentFigures, Responsiveness } from "@/lib/api/types";
import type { ReactNode } from "react";

function median(value: number | null, unit: "days" | "hours"): ReactNode {
  if (value === null) return <span className="text-ink-soft">not enough to say</span>;
  return unit === "days" ? `${formatDays(value)} days` : `${value < 1 ? "under 1" : Math.round(value)} hours`;
}

function reportLines(department: DepartmentFigures, waitingDays: number): Line[] {
  const r = department.reports;
  const id = `responsiveness-${department.id}`;
  return [
    { label: "Received", value: <CountValue value={r.received} />, testId: `${id}-received` },
    { label: "Resolved", value: <CountValue value={r.resolved} />, testId: `${id}-resolved` },
    { label: "Still open", value: <CountValue value={r.open} />, testId: `${id}-open` },
    { label: `Still waiting to be started after ${waitingDays} days`, value: <CountValue value={r.waiting} />, testId: `${id}-waiting` },
    { label: "Median time until work started", value: median(r.median_days_to_start, "days"), testId: `${id}-start` },
    { label: "Median time to resolve", value: median(r.median_days_to_resolve, "days"), testId: `${id}-resolve` },
    { label: "Resolutions residents said weren't fixed", value: <CountValue value={r.disputed} />, testId: `${id}-disputed` },
    { label: "…confirmed by the MCE", value: <CountValue value={r.confirmed} />, testId: `${id}-confirmed` },
    { label: "…sent back to be finished", value: <CountValue value={r.reopened} />, testId: `${id}-reopened` },
  ];
}

function documentLines(department: DepartmentFigures): Line[] {
  const d = department.documents;
  const id = `responsiveness-${department.id}`;
  return [
    { label: "Accepted", value: <CountValue value={d.accepted} />, testId: `${id}-accepted` },
    { label: "Disputed", value: <CountValue value={d.disputed} />, testId: `${id}-disputed-documents` },
    { label: "Left to publish automatically (72 hours ran out)", value: <CountValue value={d.auto_published} />, testId: `${id}-auto` },
    { label: "Median time to review", value: median(d.median_hours_to_review, "hours"), testId: `${id}-review` },
  ];
}

function DepartmentCard({ department, waitingDays }: { department: DepartmentFigures; waitingDays: number }) {
  return (
    <article className="flex flex-col gap-4 rounded-xl border bg-card p-4 sm:p-5" data-testid={`responsiveness-${department.id}`}>
      <h2 className="text-[18px]">{department.name}</h2>
      <Lines title="Residents' reports" lines={reportLines(department, waitingDays)} />
      <Lines title="Contributors' documents" lines={documentLines(department)} />
    </article>
  );
}

function Mce({ figures }: { figures: Responsiveness }) {
  const m = figures.mce;
  return (
    <article className="flex flex-col gap-4 rounded-xl border bg-card p-4 sm:p-5" data-testid="responsiveness-mce">
      <h2 className="text-[18px]">The MCE</h2>
      <Lines title="Rulings" lines={[
        { label: "Resolutions residents disputed, confirmed", value: <CountValue value={m.reports_confirmed} />, testId: "responsiveness-mce-confirmed" },
        { label: "…sent back to be finished", value: <CountValue value={m.reports_reopened} />, testId: "responsiveness-mce-reopened" },
        { label: "Escalated document disputes ruled on", value: <CountValue value={m.documents_ruled} />, testId: "responsiveness-mce-ruled" },
        { label: "…left for the clock to run out", value: <CountValue value={m.documents_run_out} />, testId: "responsiveness-mce-run-out" },
      ]} />
    </article>
  );
}

function Method({ figures }: { figures: Responsiveness }) {
  return (
    <div className="flex flex-col gap-2 rounded-xl border bg-card p-4 text-[13.5px] sm:p-5" data-testid="responsiveness-method">
      <p>
        The last twelve months, from {formatDate(figures.period_start)}. Reports about someone&apos;s personal safety are never counted, so a
        department whose work is mostly personal safety, like Social Welfare, looks quieter here than it is. A count from 1 to 4 reads
        &ldquo;fewer than 5&rdquo;, a median is given once there are five cases, and where two counts add up to one that&apos;s shown, hiding one
        hides the other. No report&apos;s content appears.
      </p>
      <p className="text-ink-soft">
        Reports don&apos;t expire, so &ldquo;still waiting to be started after {figures.waiting_days} days&rdquo; is the measure we chose for a
        report nobody has picked up. It isn&apos;t a statutory deadline. What does run out is a review clock: a contributor&apos;s document a
        department doesn&apos;t review within 72 hours publishes automatically.
      </p>
      <p className="text-ink-soft">
        Departments are listed by name, never ranked: their numbers depend on what residents report, and a blocked drain takes longer than a
        streetlight. A report sent to two departments counts for both, and one the MCE moved counts for the department that has it now. The
        Ghana Police Service and the Ghana National Fire Service receive public-safety reports too, but they are national agencies, not
        Assembly departments, so they aren&apos;t held to an Assembly scorecard.
      </p>
    </div>
  );
}

export function ResponsivenessPage() {
  const figures = useResponsiveness();
  const data = figures.data;
  const active = data?.departments.filter(isActive) ?? [];
  const quiet = data?.departments.filter((d) => !isActive(d)) ?? [];
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-7">
      <PageIntro eyebrow="Accountability" title="How departments respond">
        Evidence about the Assembly&apos;s own behaviour: how quickly each department starts and resolves what residents report, and how it
        handles the documents contributors send it.
      </PageIntro>
      <OtherView href="/accountability/documents" title="What the Assembly publishes" testId="responsiveness-to-record">
        The same Assembly measured by the documents it is required to publish.
      </OtherView>
      {figures.isPending ? <LoadingPanel label="Counting…" /> : null}
      {figures.error ? <ErrorPanel message={figures.error.message} onRetry={() => figures.refetch()} /> : null}
      {data ? (
        <>
          <Method figures={data} />
          <div className="grid gap-4 md:grid-cols-2">
            {active.map((department) => <DepartmentCard key={department.id} department={department} waitingDays={data.waiting_days} />)}
            <Mce figures={data} />
            <PetitionFigures figures={data.petitions} />
          </div>
          {quiet.length ? (
            <p className="text-[13.5px] text-ink-soft" data-testid="responsiveness-quiet">
              Nothing counted here in the last twelve months (personal-safety reports are never counted): {quiet.map((d) => d.name).join(", ")}.
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
