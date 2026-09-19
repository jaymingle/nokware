"use client";

import { CheckIcon, CopyIcon, MessageCircleIcon } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { PhotoGallery } from "@/components/cases/photo-gallery";
import { ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { PageShell } from "@/components/page-shell";
import { DocumentLine, LedgerMatches } from "@/components/petitions/ledger-matches";
import { MceResponse } from "@/components/petitions/mce-response";
import { Progress } from "@/components/petitions/petition-card";
import { PetitionTombstoneView } from "@/components/petitions/petition-tombstone";
import { PetitionVersions } from "@/components/petitions/petition-versions";
import { ReportPetition } from "@/components/petitions/report-petition";
import { SignPanel } from "@/components/petitions/sign-panel";
import { Signers } from "@/components/petitions/signers";
import { StatusMark, StatusTag } from "@/components/status-tag";
import { Button } from "@/components/ui/button";
import { useMounted } from "@/hooks/use-mounted";
import { useNow } from "@/hooks/use-now";
import { ApiError } from "@/lib/api/errors";
import { usePetition, usePetitionLedger, usePetitionOptions } from "@/lib/api/petition-queries";
import {
  closingLine, earlierVersionsLine, placeLine, publishedLine, removedBeforeLine, responseLine, spacedCode, startedBy,
  timelineText, whatsappShareUrl,
} from "@/lib/petitions";
import { issueStage, petitionEventTone, petitionStatus } from "@/lib/status";
import { joinNames } from "@/lib/text";
import { formatDate } from "@/lib/time";
import { voicesLine } from "@/lib/voices";

import type { PetitionDetail } from "@/lib/api/types";

function Section({ title, children, testId }: { title: string; children: ReactNode; testId: string }) {
  return (
    <section className="flex flex-col gap-3 rounded-xl border bg-card p-5" data-testid={testId}>
      <h2 className="text-[19px]">{title}</h2>
      {children}
    </section>
  );
}

function Standing({ petition, now }: { petition: PetitionDetail; now: number }) {
  const options = usePetitionOptions();
  const days = options.data?.response_days ?? 30;
  const response = responseLine(petition, now);
  const tag = petitionStatus(petition.status);
  const earlier = earlierVersionsLine(petition.signatures_on_earlier_versions);
  const removed = removedBeforeLine(petition.removals);
  return (
    <div className="flex flex-col gap-3 rounded-xl border bg-card p-5" data-testid="petition-standing">
      <div><StatusTag tone={tag.tone} testId="petition-status">{tag.label}</StatusTag></div>
      <Progress signatures={petition.signatures} threshold={petition.threshold} large />
      {earlier ? <p className="text-[12.5px] text-ink-soft" data-testid="petition-earlier-versions">{earlier}</p> : null}
      {response ? <p className="rounded-lg bg-gold-tint px-3 py-2.5 text-[14px]" data-testid="petition-response-due">{response}</p> : null}
      <p className="text-[13.5px]" data-testid="petition-closing">{closingLine(petition, now)}</p>
      {removed ? <p className="text-[13.5px] text-ink-soft" data-testid="petition-removals">{removed}</p> : null}
      {petition.status === "open" && petition.threshold ? (
        <p className="text-[13.5px] text-ink-soft">
          If it reaches {petition.threshold.toLocaleString()} signatures, it goes to the MCE, who then has {days} days to respond
          publicly on this page.
        </p>
      ) : null}
    </div>
  );
}

function Share({ petition }: { petition: PetitionDetail }) {
  const mounted = useMounted();
  const [copied, setCopied] = useState(false);
  if (!mounted) return null;
  const url = `${window.location.origin}/petitions/${petition.code}`;
  const copy = async () => {
    await navigator.clipboard.writeText(url);
    setCopied(true);
  };
  return (
    <div className="flex flex-wrap gap-2" data-testid="petition-share">
      <Button asChild size="sm">
        <a href={whatsappShareUrl(petition.title, url)} target="_blank" rel="noopener noreferrer" data-testid="petition-share-whatsapp">
          <MessageCircleIcon data-icon="inline-start" /> Share on WhatsApp
        </a>
      </Button>
      <Button variant="secondary" size="sm" onClick={() => void copy()} data-testid="petition-share-copy">
        {copied ? <CheckIcon data-icon="inline-start" /> : <CopyIcon data-icon="inline-start" />}
        {copied ? "Link copied" : "Copy the link"}
      </Button>
    </div>
  );
}

function Cited({ petition }: { petition: PetitionDetail }) {
  const issue = petition.issue;
  if (!issue && petition.documents.length === 0) return null;
  return (
    <Section title="What the petition cites" testId="petition-cited">
      {issue ? (
        <div className="rounded-lg bg-paper-subtle px-4 py-3 text-[13.5px]" data-testid="petition-issue">
          <p className="font-medium">An issue residents reported: {issue.topic}{issue.ward ? ` in ${issue.ward}` : ""}</p>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-[12.5px] text-ink-soft">
            <StatusTag tone={issueStage(issue.stage).tone}>{issueStage(issue.stage).label}</StatusTag>
            {voicesLine(issue.voices)}
          </p>
        </div>
      ) : null}
      {petition.documents.map((doc) => <DocumentLine key={doc.id} doc={doc} />)}
    </Section>
  );
}

function LedgerContext({ code }: { code: string }) {
  const ledger = usePetitionLedger(code);
  return (
    <Section title="What The Ledger already holds on this" testId="petition-ledger">
      {ledger.isPending ? <p className="text-[13.5px] text-ink-soft">Searching the Assembly&apos;s documents…</p> : null}
      {ledger.error ? <p className="text-[13.5px] text-brick">{ledger.error.message}</p> : null}
      {ledger.data ? <LedgerMatches matches={ledger.data} testId="petition-ledger-matches" /> : null}
    </Section>
  );
}

function Timeline({ petition }: { petition: PetitionDetail }) {
  return (
    <Section title="What has happened" testId="petition-timeline">
      <ol className="flex flex-col gap-2 text-[13.5px]">
        {petition.timeline.map((entry) => (
          <li key={`${entry.action}-${entry.at}`} className="flex flex-wrap items-baseline gap-x-3">
            <span className="flex w-28 shrink-0 items-center gap-2 text-ink-soft tabular-nums">
              <StatusMark tone={petitionEventTone(entry.action)} className="size-3.5" />
              {formatDate(entry.at)}
            </span>
            <span>{timelineText(entry)}</span>
          </li>
        ))}
      </ol>
    </Section>
  );
}

/** A petition edited once has a history worth a heading; one that never changed has nothing to say. */
function History({ petition }: { petition: PetitionDetail }) {
  if (petition.versions.length < 2 && petition.signatures_on_earlier_versions === 0) return null;
  return (
    <Section title="How the words have changed" testId="petition-history">
      <PetitionVersions versions={petition.versions} onEarlier={petition.signatures_on_earlier_versions} />
    </Section>
  );
}

function signable(petition: PetitionDetail, now: number): boolean {
  return (petition.status === "open" || petition.status === "awaiting_response") && !!petition.closes_at && Date.parse(petition.closes_at) > now;
}

function Petition({ petition }: { petition: PetitionDetail }) {
  const now = useNow();
  const byline = [startedBy(petition.started_by), publishedLine(petition)].filter(Boolean).join(" · ");
  return (
    <PageShell
      eyebrow={`Petition ${spacedCode(petition.code)} · ${petition.topic}`}
      title={petition.title}
      lead={
        <span className="flex flex-col gap-1.5">
          <span>To the Accra Metropolitan Assembly, concerning {joinNames(petition.departments)}. {placeLine(petition)}.</span>
          <span className="text-[13px]" data-testid="petition-byline">{byline}</span>
        </span>
      }
    >
      <Standing petition={petition} now={now} />
      <MceResponse petition={petition} />
      {signable(petition, now) ? <SignPanel petition={petition} /> : null}
      <Share petition={petition} />
      <Section title="Why" testId="petition-body">
        <p className="text-[15px] whitespace-pre-line">{petition.body}</p>
        {/* The same viewer a case's photos open in: one way of looking at a photo across Nokware. */}
        <PhotoGallery photos={petition.images} testIdPrefix="petition-image" subject="on this petition" />
      </Section>
      <Signers code={petition.code} signatures={petition.signatures} />
      <Cited petition={petition} />
      <LedgerContext code={petition.code} />
      <History petition={petition} />
      <Timeline petition={petition} />
      <div className="flex"><ReportPetition code={petition.code} /></div>
    </PageShell>
  );
}

/** A number nobody has used. Its own heading, so this state has an h1 like every other. */
function NotFound({ message }: { message: string }) {
  return (
    <PageShell eyebrow="Petitions" title="Petition not found">
      <p className="text-[15px]" data-testid="petition-not-found">{message}</p>
      <div>
        <Button asChild variant="secondary"><Link href="/petitions" data-testid="petition-not-found-list">See the petitions</Link></Button>
      </div>
    </PageShell>
  );
}

export function PetitionPage({ code }: { code: string }) {
  const petition = usePetition(code);
  // A petition's page is titled with the petition, which isn't known yet — so the heading says what the page is.
  if (petition.isPending) {
    return <PageShell eyebrow="Petitions" title="Petition"><LoadingPanel label="Loading the petition…" /></PageShell>;
  }
  if (petition.error) {
    if (petition.error instanceof ApiError && petition.error.status === 404) return <NotFound message={petition.error.message} />;
    return (
      <PageShell eyebrow="Petitions" title="Petition">
        <ErrorPanel message={petition.error.message} onRetry={() => void petition.refetch()} />
      </PageShell>
    );
  }
  if (petition.data.state === "removed") return <PetitionTombstoneView stone={petition.data} />;
  return <Petition petition={petition.data} />;
}
