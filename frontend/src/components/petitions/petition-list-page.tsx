"use client";

import Link from "next/link";
import { useState } from "react";

import { ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { PageShell } from "@/components/page-shell";
import { PetitionCard } from "@/components/petitions/petition-card";
import { RemovalRecord } from "@/components/petitions/removal-record";
import { TombstoneCard } from "@/components/petitions/tombstone-card";
import { StatusMark } from "@/components/status-tag";
import { Button } from "@/components/ui/button";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { useNow } from "@/hooks/use-now";
import { usePetitions } from "@/lib/api/petition-queries";
import { PETITION_GROUPS } from "@/lib/status";
import { cn } from "@/lib/utils";

import type { PetitionGroup } from "@/lib/api/petitions";
import type { PetitionPage } from "@/lib/api/types";

const PAGE = 20;

const TABS: { id: PetitionGroup; label: string }[] = [
  { id: "open", label: "Open" }, { id: "awaiting", label: "With the MCE" }, { id: "responded", label: "Responded" },
  { id: "removed", label: "Removed" }, { id: "closed", label: "Closed" },
];
const EMPTY: Record<PetitionGroup, string> = {
  open: "No petitions are open yet.",
  awaiting: "No petition has reached its signatures yet.",
  responded: "The MCE hasn't answered a petition yet.",
  closed: "No petitions have closed yet.",
  removed: "No petition has been taken down.",
};

type TabsProps = { tab: PetitionGroup; page: PetitionPage | undefined; onTab: (tab: PetitionGroup) => void };

function Tabs({ tab, page, onTab }: TabsProps) {
  return (
    <div role="tablist" aria-label="Petitions" className="flex max-w-full gap-1 overflow-x-auto rounded-lg bg-paper-subtle p-1">
      {TABS.map((t) => {
        const count = page?.counts[t.id];
        return (
          <button key={t.id} type="button" role="tab" aria-selected={tab === t.id} onClick={() => onTab(t.id)}
            // The number is part of the label a screen reader reads, not a decoration beside it.
            aria-label={count === undefined ? t.label : `${t.label}, ${count} ${count === 1 ? "petition" : "petitions"}`}
            className={cn("flex shrink-0 items-center gap-1.5 rounded-md px-3 py-1.5 text-[13.5px]", tab === t.id ? "bg-card font-medium shadow-sm" : "text-ink-soft")}
            data-testid={`petitions-tab-${t.id}`}>
            <StatusMark tone={PETITION_GROUPS[t.id]} className="size-3.5" />
            {t.label}
            {count === undefined ? null : (
              <span aria-hidden className={cn("tabular-nums", tab === t.id ? "text-ink-soft" : "text-ink-soft/70")} data-testid={`petitions-count-${t.id}`}>
                {count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function Empty({ group }: { group: PetitionGroup }) {
  return <p className="py-4 text-[14px] text-ink-soft" data-testid="petitions-empty">{EMPTY[group]}</p>;
}

function Listing({ page, group, now }: { page: PetitionPage; group: PetitionGroup; now: number }) {
  if (group === "removed") {
    if (page.removed.length === 0) return <Empty group={group} />;
    return <ul data-testid="petitions-removed">{page.removed.map((s) => <TombstoneCard key={s.code} stone={s} />)}</ul>;
  }
  if (page.petitions.length === 0) return <Empty group={group} />;
  return <ul>{page.petitions.map((p) => <PetitionCard key={p.code} petition={p} now={now} />)}</ul>;
}

function Paging({ total, offset, onOffset }: { total: number; offset: number; onOffset: (offset: number) => void }) {
  if (total <= PAGE) return null;
  return (
    <div className="flex items-center gap-3 text-[13px] text-ink-soft">
      <Button variant="secondary" size="sm" disabled={offset === 0} onClick={() => onOffset(offset - PAGE)} data-testid="petitions-previous">Previous</Button>
      <span>{offset + 1}–{Math.min(offset + PAGE, total)} of {total}</span>
      <Button variant="secondary" size="sm" disabled={offset + PAGE >= total} onClick={() => onOffset(offset + PAGE)} data-testid="petitions-next">Next</Button>
    </div>
  );
}

type ToolbarProps = {
  tab: PetitionGroup; page: PetitionPage | undefined; topic: string;
  onTab: (tab: PetitionGroup) => void; onTopic: (topic: string) => void;
};

/** A tombstone has no topic: reading one off the petition is what the tombstone exists to prevent. */
function Toolbar({ tab, page, topic, onTab, onTopic }: ToolbarProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Tabs tab={tab} page={page} onTab={onTab} />
      {tab === "removed" ? null : (
        <NativeSelect value={topic} onChange={(e) => onTopic(e.target.value)} aria-label="Topic" size="sm" data-testid="petitions-topic">
          <NativeSelectOption value="">All topics</NativeSelectOption>
          {page?.topics.map((t) => <NativeSelectOption key={t.id} value={t.id}>{t.name}</NativeSelectOption>)}
        </NativeSelect>
      )}
    </div>
  );
}

type BodyProps = { page: PetitionPage; group: PetitionGroup; now: number; offset: number; onOffset: (offset: number) => void };

/** The removed group is the grounds they came down on, and then the tombstones themselves. */
function Body({ page, group, now, offset, onOffset }: BodyProps) {
  return (
    <>
      {group === "removed" ? <RemovalRecord removals={page.removals} /> : null}
      <Listing page={page} group={group} now={now} />
      <Paging total={page.total} offset={offset} onOffset={onOffset} />
    </>
  );
}

export function PetitionListPage() {
  const [tab, setTab] = useState<PetitionGroup>("open");
  const [topic, setTopic] = useState("");
  const [offset, setOffset] = useState(0);
  const now = useNow();
  const petitions = usePetitions({ group: tab, topic: tab === "removed" ? "" : topic, limit: PAGE, offset });
  const choose = (next: PetitionGroup) => { setTab(next); setOffset(0); };
  return (
    <PageShell
      eyebrow="Petitions"
      title="Ask the Assembly to act"
      lead={
        <>
          Residents asking the Accra Metropolitan Assembly to do something, and the support each has gathered. Nobody
          approves a petition: the person who writes it publishes it, and the MCE decides only whether to answer.
        </>
      }
      actions={
        <>
          <Button asChild><Link href="/petitions/new" data-testid="petitions-start">Start a petition</Link></Button>
          <Button asChild variant="secondary"><Link href="/petitions/mine" data-testid="petitions-mine">Your petitions</Link></Button>
        </>
      }
    >
      {petitions.error ? <ErrorPanel message={petitions.error.message} onRetry={() => void petitions.refetch()} /> : null}
      <section className="flex flex-col gap-3 rounded-xl border bg-card p-5" aria-label="Petitions">
        <Toolbar tab={tab} page={petitions.data} topic={topic} onTab={choose} onTopic={(next) => { setTopic(next); setOffset(0); }} />
        {petitions.isPending ? <LoadingPanel label="Loading petitions…" /> : null}
        {petitions.data ? <Body page={petitions.data} group={tab} now={now} offset={offset} onOffset={setOffset} /> : null}
      </section>
    </PageShell>
  );
}
