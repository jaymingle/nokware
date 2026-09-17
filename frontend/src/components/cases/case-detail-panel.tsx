"use client";

import { PhoneIcon, UsersIcon } from "lucide-react";
import Image from "next/image";

import { CaseActions } from "@/components/cases/case-actions";
import { SharedLocation } from "@/components/cases/shared-location";
import { ErrorNote } from "@/components/documents/panels";
import { Tag } from "@/components/documents/tag";
import { useCase } from "@/lib/api/queries";
import { caseEventText, caseStatusTag, SEVERITY_LABELS } from "@/lib/cases";
import { formatDateTime } from "@/lib/time";
import { voicesTally } from "@/lib/voices";

import type { CaseDetail, Option } from "@/lib/api/types";

function Facts({ detail }: { detail: CaseDetail }) {
  const facts = [
    ["Filed", formatDateTime(detail.submitted_at)],
    ["Where", detail.place ?? (detail.view === "oversight" ? "Not shown" : "Not given")],
    ["Severity", `${detail.severity} of 5 · ${SEVERITY_LABELS[detail.severity] ?? ""}`],
    ["With", detail.recipients.join(" and ")],
  ];
  return (
    <dl className="grid grid-cols-[auto_minmax(0,1fr)] gap-x-4 gap-y-1.5 text-[13px]">
      {facts.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-ink-soft">{label}</dt>
          <dd className="break-words">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Photos({ photos }: { photos: string[] }) {
  if (photos.length === 0) return null;
  return (
    <ul className="grid grid-cols-3 gap-2" aria-label="Photos">
      {photos.map((url, index) => (
        <li key={url}>
          <a href={url} target="_blank" rel="noopener noreferrer" data-testid={`case-photo-${index}`}>
            <Image src={url} alt={`Photo ${index + 1} from the citizen`} width={160} height={120} unoptimized className="aspect-4/3 w-full rounded-md border object-cover" />
          </a>
        </li>
      ))}
    </ul>
  );
}

function Callback({ detail }: { detail: CaseDetail }) {
  if (!detail.contact) return null;
  const numbers = [detail.contact.phone, detail.contact.whatsapp].filter((n): n is string => Boolean(n));
  return (
    <div className="flex flex-col gap-1 rounded-lg bg-teal-tint px-3.5 py-3 text-[13px]" data-testid={`case-contact-${detail.case_id}`}>
      <p className="font-medium text-teal">The citizen allowed a call about this case</p>
      {numbers.map((number) => (
        <a key={number} href={`tel:${number}`} className="inline-flex items-center gap-1.5 text-teal underline underline-offset-2">
          <PhoneIcon aria-hidden className="size-3.5" />
          {number}
        </a>
      ))}
    </div>
  );
}

function Trail({ detail }: { detail: CaseDetail }) {
  return (
    <div className="flex flex-col gap-2.5">
      <p className="text-[12.5px] text-ink-soft">Chain of custody</p>
      <ol className="flex flex-col gap-3" data-testid={`case-trail-${detail.case_id}`}>
        {detail.history.map((event, index) => (
          <li key={`${event.at}-${index}`} className="grid grid-cols-[12px_minmax(0,1fr)] gap-2.5">
            <span aria-hidden className="mt-[7px] size-[5px] rounded-full bg-teal" />
            <div>
              <p className="text-[13px] break-words">{caseEventText(event)}</p>
              <p className="text-[12px] text-ink-soft tabular-nums">{event.actor_name} · {formatDateTime(event.at)}</p>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

function Body({ detail }: { detail: CaseDetail }) {
  if (detail.view === "oversight") {
    return (
      <p className="rounded-lg bg-paper-subtle px-3.5 py-3 text-[13px] text-ink-soft">
        A personal-safety report. Only {detail.recipients.join(" and ")} can read it; you see its progress and audit trail.
      </p>
    );
  }
  return (
    <>
      <p className="text-[14.5px] whitespace-pre-line break-words">{detail.description}</p>
      <Photos photos={detail.photos} />
      {detail.escalation_note ? (
        <p className="rounded-lg bg-brick-tint px-3.5 py-3 text-[13px]"><span className="font-medium text-brick">The citizen escalated it: </span>{detail.escalation_note}</p>
      ) : null}
      <Callback detail={detail} />
      <SharedLocation key={detail.case_id} detail={detail} />
    </>
  );
}

function Voices({ detail }: { detail: CaseDetail }) {
  if (!detail.voices) return null;
  const names = detail.voice_names ?? [];
  return (
    <div className="flex flex-col gap-1 rounded-lg border px-3.5 py-3 text-[13px]" data-testid={`case-voices-${detail.case_id}`}>
      <p className="flex items-center gap-1.5 font-medium">
        <UsersIcon aria-hidden className="size-4 text-teal" />
        {voicesTally(detail.voices)}: it affects them too
      </p>
      {detail.voice_names !== null ? (
        <p className="text-ink-soft">
          {names.length ? `${names.length} gave a name: ${names.join(", ")}.` : "No one gave a name."} Names are deleted 30 days after the case closes.
        </p>
      ) : null}
    </div>
  );
}

function Loaded({ detail, recipients }: { detail: CaseDetail; recipients?: Option[] }) {
  const tag = caseStatusTag(detail);
  return (
    <div className="flex flex-col gap-4" data-testid={`case-detail-${detail.case_id}`}>
      <div className="flex flex-wrap items-center gap-2.5">
        <span className="text-[12.5px] text-ink-soft tabular-nums">{detail.reference}</span>
        <Tag tone={tag.tone}>{tag.label}</Tag>
        {detail.needs_routing ? <Tag tone="gold">Needs routing</Tag> : null}
      </div>
      <h2 className="text-[22px] leading-snug">{detail.topic}</h2>
      <Body detail={detail} />
      <Voices detail={detail} />
      <Facts detail={detail} />
      <CaseActions detail={detail} recipients={recipients} />
      <Trail detail={detail} />
    </div>
  );
}

export function CaseDetailPanel({ caseId, recipients }: { caseId: string | null; recipients?: Option[] }) {
  const { data, error, isPending } = useCase(caseId);
  if (!caseId) return <p className="text-[13.5px] text-ink-soft">Select a case to read it, see its history and move it along.</p>;
  if (isPending) return <p className="text-[13.5px] text-ink-soft" aria-live="polite">Loading the case…</p>;
  if (error) return <ErrorNote>{error.message}</ErrorNote>;
  return <Loaded detail={data} recipients={recipients} />;
}
