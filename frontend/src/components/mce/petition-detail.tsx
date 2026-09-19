"use client";

import { ArrowLeftIcon } from "lucide-react";
import Link from "next/link";

import { ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { RespondDialog } from "@/components/mce/respond-dialog";
import { DocumentLine } from "@/components/petitions/ledger-matches";
import { Progress } from "@/components/petitions/petition-card";
import { PetitionVersions } from "@/components/petitions/petition-versions";
import { StatusMark, StatusTag } from "@/components/status-tag";
import { useNow } from "@/hooks/use-now";
import { usePetition } from "@/lib/api/petition-queries";
import {
  closingLine, daysLeft, placeLine, previousRemovalsLine, removedBeforeLine, removedLine, responseLine, spacedCode,
  startedBy, timelineText,
} from "@/lib/petitions";
import { petitionEventTone, petitionStatus } from "@/lib/status";
import { joinNames } from "@/lib/text";
import { formatDate } from "@/lib/time";

import type { PetitionDetail, PetitionResponseOut, PetitionTombstone } from "@/lib/api/types";
import type { ReactNode } from "react";

/**
 * One petition as the MCE reads it. Everything a contributor did to it is here to be read and nothing more: this
 * office answers petitions, it doesn't moderate them, and a target with a delete button is not accountability.
 */

function Section({ title, testId, children }: { title: string; testId: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3 rounded-xl border bg-card p-5" data-testid={testId}>
      <h2 className="text-[19px]">{title}</h2>
      {children}
    </section>
  );
}

function BackLink() {
  return (
    <Link href="/portal/mce/petitions" className="flex w-fit items-center gap-1.5 text-[13.5px] underline underline-offset-2"
      data-testid="mce-petition-back">
      <ArrowLeftIcon aria-hidden className="size-3.5" /> All petitions
    </Link>
  );
}

function Words({ petition }: { petition: PetitionDetail }) {
  return (
    <Section title="The petition" testId="mce-petition-words">
      <p className="text-[12.5px] text-ink-soft">
        No. {spacedCode(petition.code)} · {petition.topic} · {placeLine(petition)} · concerns {joinNames(petition.departments)} · {startedBy(petition.started_by)}
        {petition.published_at ? ` · published ${formatDate(petition.published_at)}` : ""}
      </p>
      <p className="text-[14.5px] whitespace-pre-line">{petition.body}</p>
      {petition.issue ? (
        <p className="text-[13px] text-ink-soft" data-testid="mce-petition-issue">
          Cites an open issue: {petition.issue.topic}{petition.issue.ward ? ` in ${petition.issue.ward}` : ""}
        </p>
      ) : null}
      {petition.documents.map((doc) => <DocumentLine key={doc.id} doc={doc} />)}
    </Section>
  );
}

function Standing({ petition, now }: { petition: PetitionDetail; now: number }) {
  const tag = petitionStatus(petition.status);
  const response = responseLine(petition, now, "on its public page");
  const late = Boolean(petition.response_due) && daysLeft(petition.response_due ?? "", now) === 0;
  return (
    <Section title="Signatures and the clock" testId="mce-petition-standing">
      <div><StatusTag tone={tag.tone} testId="mce-petition-status">{tag.label}</StatusTag></div>
      <Progress signatures={petition.signatures} threshold={petition.threshold} large />
      {response ? <p className="rounded-lg bg-gold-tint px-3 py-2.5 text-[14px]" data-testid="mce-petition-due">{response}</p> : null}
      {closingLine(petition, now) ? <p className="text-[13.5px]" data-testid="mce-petition-closing">{closingLine(petition, now)}</p> : null}
      {petition.status === "awaiting_response" ? <RespondDialog code={petition.code} late={late} /> : null}
    </Section>
  );
}

function Response({ response }: { response: PetitionResponseOut }) {
  return (
    <Section title="Your response" testId="mce-petition-response">
      <p className="text-[12.5px] text-ink-soft">
        {response.label}{response.department ? ` · ${response.department}` : ""} · published {formatDate(response.responded_at)}
        {response.late ? ` · ${response.days_late} days after the deadline` : ""}
      </p>
      <p className="text-[14.5px] whitespace-pre-line">{response.text}</p>
      {response.documents.map((doc) => <DocumentLine key={doc.id} doc={doc} />)}
    </Section>
  );
}

const NOT_YOURS =
  "Petitions are reported to contributors, not to this office, and a contributor removes one on a named ground. You can't see who reported a petition, and you can't take one down: the Assembly is usually what a petition is about.";

function Moderation({ petition }: { petition: PetitionDetail }) {
  const removals = petition.timeline.filter((entry) => entry.action === "removed" || entry.action === "republished");
  return (
    <Section title="Reports and removals" testId="mce-petition-moderation">
      <p className="text-[13.5px]" data-testid="mce-petition-removals">
        {removedBeforeLine(petition.removals) ?? "This petition has never been removed."}
      </p>
      {removals.length > 0 ? (
        <ul className="flex flex-col gap-1.5 text-[13.5px]">
          {removals.map((entry, index) => (
            <li key={`${entry.action}-${index}`} className="flex items-start gap-2">
              <StatusMark tone={petitionEventTone(entry.action)} className="mt-0.5 size-3.5" />
              <span>{timelineText(entry)} · {formatDate(entry.at)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <p className="text-[12.5px] text-ink-soft">{NOT_YOURS}</p>
    </Section>
  );
}

function Timeline({ petition }: { petition: PetitionDetail }) {
  return (
    <Section title="What has happened" testId="mce-petition-timeline">
      <ul className="flex flex-col gap-2 text-[13.5px]">
        {petition.timeline.map((entry, index) => (
          <li key={`${entry.action}-${index}`} className="flex items-start gap-2">
            <StatusMark tone={petitionEventTone(entry.action)} className="mt-0.5 size-3.5" />
            <span>{timelineText(entry)} · {formatDate(entry.at)}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

/** The same list the public page shows. A petition edited by nobody has one version and nothing to say about it. */
function Versions({ petition }: { petition: PetitionDetail }) {
  if (petition.versions.length < 2 && petition.signatures_on_earlier_versions === 0) return null;
  return (
    <Section title="Versions" testId="mce-petition-versions">
      <PetitionVersions versions={petition.versions} onEarlier={petition.signatures_on_earlier_versions} />
    </Section>
  );
}

function Removed({ stone }: { stone: PetitionTombstone }) {
  const tag = petitionStatus("removed");
  return (
    <div className="flex flex-col gap-4">
      <BackLink />
      <Section title={`Petition ${spacedCode(stone.code)} was removed`} testId="mce-petition-removed">
        <div><StatusTag tone={tag.tone} testId="mce-petition-status">{tag.label}</StatusTag></div>
        <p className="text-[14.5px]">{removedLine(stone)}</p>
        {stone.duplicate_of ? <p className="text-[13.5px]">It duplicated petition {spacedCode(stone.duplicate_of)}.</p> : null}
        {previousRemovalsLine(stone.previous_removals) ? (
          <p className="text-[13.5px] text-ink-soft">{previousRemovalsLine(stone.previous_removals)}</p>
        ) : null}
        <p className="text-[12.5px] text-ink-soft">
          Nothing of the petition is kept once it comes down — no title, body, image, signature count or answer. {NOT_YOURS}
        </p>
      </Section>
    </div>
  );
}

function Found({ petition, now }: { petition: PetitionDetail; now: number }) {
  return (
    <div className="flex flex-col gap-4">
      <BackLink />
      <p className="font-heading text-[26px] leading-snug" data-testid="mce-petition-title">{petition.title}</p>
      <Standing petition={petition} now={now} />
      <Words petition={petition} />
      {petition.response ? <Response response={petition.response} /> : null}
      <Versions petition={petition} />
      <Moderation petition={petition} />
      <Timeline petition={petition} />
    </div>
  );
}

export function McePetition({ code }: { code: string }) {
  const now = useNow();
  const { data, error, isPending, refetch } = usePetition(code);
  if (isPending) return <LoadingPanel label="Loading the petition…" />;
  if (error) return <ErrorPanel message={error.message} onRetry={() => void refetch()} />;
  return data.state === "removed" ? <Removed stone={data} /> : <Found petition={data} now={now} />;
}
