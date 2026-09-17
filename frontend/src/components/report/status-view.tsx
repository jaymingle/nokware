import { ContactList } from "@/components/contacts/contact-list";
import { Tag } from "@/components/documents/tag";
import { ReadAloud } from "@/components/read-aloud/read-aloud";
import { EscalateForm } from "@/components/report/escalate-form";
import { Card, CardContent } from "@/components/ui/card";
import { reportAudio } from "@/lib/api/public";
import { STAGES, stageLabels, stageOf, statusTag } from "@/lib/report/status";
import { joinNames } from "@/lib/text";
import { formatDate, formatDateTime } from "@/lib/time";
import { cn } from "@/lib/utils";

import type { LocationViewNote, ReportStatus } from "@/lib/api/types";
import type { ReactNode } from "react";

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

export function CivicStatus({ status }: { status: ReportStatus }) {
  const where = [status.ward, status.sub_metro ? `${status.sub_metro} sub-metro` : null].filter(Boolean).join(", ");
  return (
    <StatusFrame status={status}>
      <ReadAloud load={(part) => reportAudio(status.reference, "status", part)} label="Listen to this report's status" testId="status-listen" />
      <dl className="flex flex-col gap-3">
        <Detail label="What">{status.topic}</Detail>
        {where ? <Detail label="Where">{where}</Detail> : null}
        <Detail label="Sent to">{joinNames(status.recipients ?? [])}</Detail>
        {status.resolved_at && status.status === "resolved" ? <Detail label="Resolved">{formatDate(status.resolved_at)}</Detail> : null}
      </dl>
      {status.voices ? (
        <p className="text-[13.5px]" data-testid="status-voices">
          {status.voices.toLocaleString()} other {status.voices === 1 ? "resident says" : "residents say"} this affects them too.
        </p>
      ) : null}
      <ResolutionNotes status={status} />
      <CivicFollowUp status={status} />
      <ContactList title="Numbers for this report" contacts={status.contacts ?? []} testId="status-contacts" />
    </StatusFrame>
  );
}

/** The citizen gave their location for a reason and should know each time it was used. */
function LocationViews({ views }: { views: LocationViewNote[] }) {
  if (views.length === 0) return null;
  return (
    <ul className="flex flex-col gap-1.5 rounded-lg bg-paper-subtle px-3.5 py-3 text-[13.5px]" data-testid="status-location-views">
      {views.map((view) => (
        <li key={view.at}>Your location was viewed by {view.by} on {formatDateTime(view.at)}.</li>
      ))}
    </ul>
  );
}

/** Progress only: anyone with the reference can open this. */
export function PrivateStatus({ status }: { status: ReportStatus }) {
  return (
    <StatusFrame status={status}>
      <p className="text-[13.5px] text-ink-soft">This page shows only how far along the case is. Nothing about what was reported appears here.</p>
      <LocationViews views={status.location_views ?? []} />
      {status.escalate_until ? (
        <EscalateForm reference={status.reference} until={status.escalate_until} intro="Not satisfied with how this was handled? You can ask for a review." action="Ask for a review" />
      ) : null}
      {status.escalated && !status.escalate_until ? <p className="border-t pt-5 text-[14px]" data-testid="status-escalated">Your request for a review has been received.</p> : null}
    </StatusFrame>
  );
}
