"use client";

import Link from "next/link";
import { useState } from "react";

import { ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { Progress } from "@/components/petitions/petition-card";
import { StatusMark, StatusTag } from "@/components/status-tag";
import { Button } from "@/components/ui/button";
import { useNow } from "@/hooks/use-now";
import { usePetitionOptions, usePetitions } from "@/lib/api/petition-queries";
import { closingLine, placeLine, responseLine, spacedCode, startedBy } from "@/lib/petitions";
import {
  emptyGroup, groupCount, groupLabel, listedGroup, petitionHref, PORTAL_GROUPS, type PortalPetitionGroup,
} from "@/lib/portal/petitions";
import { petitionStatus, PETITION_GROUPS } from "@/lib/status";
import { joinNames, plural } from "@/lib/text";
import { cn } from "@/lib/utils";

import type { PetitionCard, PetitionPage, PetitionRemovals } from "@/lib/api/types";

const PAGE = 50;

function Chip({ group, page, chosen, onChoose, words }: {
  group: PortalPetitionGroup; page?: PetitionPage; chosen: boolean;
  onChoose: () => void; words?: Record<string, string>;
}) {
  const label = groupLabel(group, words);
  const count = groupCount(group, page);
  return (
    <button type="button" role="tab" aria-selected={chosen} onClick={onChoose}
      aria-label={count === undefined ? label : `${label}, ${plural(count, "petition", "petitions")}`}
      className={cn("flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-[13.5px]",
        chosen ? "bg-card font-medium shadow-sm" : "text-ink-soft")}
      data-testid={`mce-petitions-tab-${group}`}>
      <StatusMark tone={PETITION_GROUPS[group]} className="size-3.5" />
      {label}
      {count === undefined ? null : (
        <span aria-hidden className="tabular-nums text-ink-soft" data-testid={`mce-petitions-count-${group}`}>{count}</span>
      )}
    </button>
  );
}

function Chips({ group, page, onGroup }: { group: PortalPetitionGroup; page?: PetitionPage; onGroup: (g: PortalPetitionGroup) => void }) {
  const words = usePetitionOptions().data?.status_words;
  return (
    <div role="tablist" aria-label="Petitions" className="flex max-w-full gap-1 overflow-x-auto rounded-lg bg-paper-subtle p-1">
      {PORTAL_GROUPS.map((g) => (
        <Chip key={g} group={g} page={page} words={words} chosen={group === g} onChoose={() => onGroup(g)} />
      ))}
    </div>
  );
}

function Row({ petition, now }: { petition: PetitionCard; now: number }) {
  const tag = petitionStatus(petition.status);
  return (
    <li className="flex flex-col gap-2 border-b py-4 last:border-0" data-testid={`mce-petition-${petition.code}`}>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        <Link href={petitionHref(petition.code)} className="text-[16px] font-medium underline underline-offset-2"
          data-testid={`mce-petition-${petition.code}-link`}>
          {petition.title}
        </Link>
        <StatusTag tone={tag.tone} testId={`mce-petition-${petition.code}-status`}>{tag.label}</StatusTag>
      </div>
      <p className="text-[12.5px] text-ink-soft">
        No. {spacedCode(petition.code)} · {petition.topic} · {placeLine(petition)} · concerns {joinNames(petition.departments)} · {startedBy(petition.started_by)}
      </p>
      <div className="max-w-sm"><Progress signatures={petition.signatures} threshold={petition.threshold} /></div>
      <p className="text-[12.5px] text-ink-soft">{responseLine(petition, now, "on its page") ?? closingLine(petition, now)}</p>
    </li>
  );
}

/** Newest first, whatever order the list arrived in: the queue is read as a queue, not as a league table. */
function newestFirst(petitions: PetitionCard[]): PetitionCard[] {
  return [...petitions].sort((a, b) => Date.parse(b.published_at ?? "") - Date.parse(a.published_at ?? ""));
}

function RemovalRecord({ removals }: { removals: PetitionRemovals }) {
  return (
    <div className="flex flex-col gap-2 py-4" data-testid="mce-petitions-removed">
      <p className="text-[14px]">
        {removals.total === 0 ? "No petition has been removed." : `${plural(removals.total, "petition has", "petitions have")} been removed.`}{" "}
        A removal is a contributor&apos;s, on one of the four grounds. Removed petitions aren&apos;t listed: each
        number still opens a page giving its ground and the date, and nothing else.
      </p>
      <ul className="flex flex-col gap-1 text-[13px] text-ink-soft">
        {removals.grounds.map((ground) => (
          <li key={ground.ground} data-testid={`mce-petitions-removed-${ground.ground}`}>
            {ground.label}: <span className="tabular-nums">{ground.count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Paging({ total, offset, onOffset }: { total: number; offset: number; onOffset: (offset: number) => void }) {
  if (total <= PAGE) return null;
  return (
    <div className="flex items-center gap-3 text-[13px] text-ink-soft">
      <Button variant="secondary" size="sm" disabled={offset === 0} onClick={() => onOffset(offset - PAGE)} data-testid="mce-petitions-previous">Previous</Button>
      <span>{offset + 1}–{Math.min(offset + PAGE, total)} of {total}</span>
      <Button variant="secondary" size="sm" disabled={offset + PAGE >= total} onClick={() => onOffset(offset + PAGE)} data-testid="mce-petitions-next">Next</Button>
    </div>
  );
}

function Listing({ page, group, now }: { page: PetitionPage; group: PortalPetitionGroup; now: number }) {
  if (group === "removed") return <RemovalRecord removals={page.removals} />;
  if (page.petitions.length === 0) {
    return <p className="py-4 text-[14px] text-ink-soft" data-testid="mce-petitions-empty">{emptyGroup(group)}</p>;
  }
  return <ul>{newestFirst(page.petitions).map((p) => <Row key={p.code} petition={p} now={now} />)}</ul>;
}

export function PetitionsQueue() {
  const [group, setGroup] = useState<PortalPetitionGroup>("awaiting");
  const [offset, setOffset] = useState(0);
  const now = useNow();
  const petitions = usePetitions({ group: listedGroup(group), topic: "", limit: PAGE, offset });
  const choose = (next: PortalPetitionGroup) => { setGroup(next); setOffset(0); };
  return (
    <section className="flex flex-col gap-3 rounded-xl border bg-card p-5" aria-label="Petitions">
      <Chips group={group} page={petitions.data} onGroup={choose} />
      {petitions.error ? <ErrorPanel message={petitions.error.message} onRetry={() => void petitions.refetch()} /> : null}
      {petitions.isPending ? <LoadingPanel label="Loading petitions…" /> : null}
      {petitions.data ? <Listing page={petitions.data} group={group} now={now} /> : null}
      {petitions.data && group !== "removed" ? <Paging total={petitions.data.total} offset={offset} onOffset={setOffset} /> : null}
    </section>
  );
}
