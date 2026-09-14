import type { ReactNode } from "react";

import { ContactList } from "@/components/contacts/contact-list";
import { Tag } from "@/components/documents/tag";
import { EscalateForm } from "@/components/report/escalate-form";
import { Card, CardContent } from "@/components/ui/card";
import { STAGES, stageLabels, stageOf, statusTag } from "@/lib/report/status";
import { joinNames } from "@/lib/text";
import { formatDate } from "@/lib/time";
import { cn } from "@/lib/utils";

import type { ReportStatus } from "@/lib/api/types";

function Steps({ status }: { status: ReportStatus }) {
  const labels = stageLabels(status.private);
  const reached = STAGES.indexOf(stageOf(status));
  return (
    <ol className="grid grid-cols-3 gap-2" aria-label="Progress" data-testid="status-steps">
      {STAGES.map((stage, index) => (
        <li key={stage} aria-current={index === reached ? "step" : undefined} className="flex flex-col gap-1.5">
          <span className={cn("h-1 rounded-full", index <= reached ? "bg-teal" : "bg-hairline")} />
          <span className={cn("text-[12.5px]", index <= reached ? "text-ink" : "text-ink-soft")}>{labels[stage]}</span>
        </li>
      ))}
    </ol>
  );
}

function StatusFrame({ status, children }: { status: ReportStatus; children: ReactNode }) {
  const tag = statusTag(status);
  return (
    <Card data-testid="status-result">
      <CardContent className="flex flex-col gap-5 py-2 sm:px-6 sm:py-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-heading text-[30px] leading-none tracking-wide tabular-nums">{status.reference}</h2>
          <Tag tone={tag.tone} testId="status-tag">{tag.label}</Tag>
        </div>
        <Steps status={status} />
        <p className="text-[13px] text-ink-soft">Reported {formatDate(status.submitted_at)}</p>
        {children}
      </CardContent>
    </Card>
  );
}

function Detail({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-0.5 sm:grid-cols-[8rem_1fr] sm:gap-3">
      <dt className="text-[12.5px] text-ink-soft sm:pt-0.5">{label}</dt>
      <dd className="text-[14.5px]">{children}</dd>
    </div>
  );
}

function ResolutionNotes({ status }: { status: ReportStatus }) {
  return (status.resolution_notes ?? []).map((note) => (
    <figure key={note.recipient} className="flex flex-col gap-1.5 rounded-lg bg-teal-tint px-4 py-3" data-testid="status-resolution-note">
      <figcaption className="text-[12.5px] text-teal">What {note.recipient} said</figcaption>
      <blockquote className="text-[14.5px] whitespace-pre-line">{note.note}</blockquote>
    </figure>
  ));
}

function CivicFollowUp({ status }: { status: ReportStatus }) {
  if (status.escalate_until) {
    return <EscalateForm reference={status.reference} until={status.escalate_until} intro="Not fixed? You can escalate it to the MCE's office." action="Escalate to the MCE's office" />;
  }
  if (status.status === "escalated") {
    return <p className="border-t pt-5 text-[14px]" data-testid="status-escalated">You escalated this report. The MCE&apos;s office will review it: it can send it back to {joinNames(status.recipients ?? [])} to finish the work, or confirm it as resolved.</p>;
  }
  if (status.escalated) {
    return <p className="border-t pt-5 text-[14px] text-ink-soft" data-testid="status-reviewed">The MCE&apos;s office has reviewed your escalation. A report can be escalated only once.</p>;
  }
  return null;
}

/** An everyday report: what, where, who has it, and what they said when they resolved it. */
export function CivicStatus({ status }: { status: ReportStatus }) {
  const where = [status.ward, status.sub_metro ? `${status.sub_metro} sub-metro` : null].filter(Boolean).join(", ");
  return (
    <StatusFrame status={status}>
      <dl className="flex flex-col gap-3">
        <Detail label="What">{status.topic}</Detail>
        {where ? <Detail label="Where">{where}</Detail> : null}
        <Detail label="Sent to">{joinNames(status.recipients ?? [])}</Detail>
        {status.resolved_at && status.status === "resolved" ? <Detail label="Resolved">{formatDate(status.resolved_at)}</Detail> : null}
      </dl>
      <ResolutionNotes status={status} />
      <CivicFollowUp status={status} />
      <ContactList title="Numbers for this report" contacts={status.contacts ?? []} testId="status-contacts" />
    </StatusFrame>
  );
}

/** A personal-safety report: how far along it is, and nothing else. Anyone with the reference can open this. */
export function PrivateStatus({ status }: { status: ReportStatus }) {
  return (
    <StatusFrame status={status}>
      <p className="text-[13.5px] text-ink-soft">This page shows only how far along the case is. Nothing about what was reported appears here.</p>
      {status.escalate_until ? (
        <EscalateForm reference={status.reference} until={status.escalate_until} intro="Not satisfied with how this was handled? You can ask for a review." action="Ask for a review" />
      ) : null}
      {status.escalated && !status.escalate_until ? <p className="border-t pt-5 text-[14px]" data-testid="status-escalated">Your request for a review has been received.</p> : null}
    </StatusFrame>
  );
}
