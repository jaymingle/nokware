"use client";

import Link from "next/link";
import { useState } from "react";

import { ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { ModerationRecord } from "@/components/petitions/moderation-record";
import { PetitionCard } from "@/components/petitions/petition-card";
import { PageIntro } from "@/components/portal/page-intro";
import { Button } from "@/components/ui/button";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { useNow } from "@/hooks/use-now";
import { usePetitions } from "@/lib/api/petition-queries";
import { cn } from "@/lib/utils";

import type { PetitionGroup } from "@/lib/api/petitions";
import type { PetitionPage } from "@/lib/api/types";

const PAGE = 20;
const GROUPS: { id: PetitionGroup; label: string }[] = [
  { id: "open", label: "Open" }, { id: "awaiting", label: "With the MCE" }, { id: "closed", label: "Closed" },
];
const EMPTY: Record<PetitionGroup, string> = {
  open: "No petitions are open yet.",
  awaiting: "No petition has reached its signatures yet.",
  closed: "No petitions have closed yet.",
};

function Tabs({ group, onGroup }: { group: PetitionGroup; onGroup: (group: PetitionGroup) => void }) {
  return (
    <div role="tablist" aria-label="Petitions" className="flex gap-1 rounded-lg bg-paper-subtle p-1">
      {GROUPS.map((g) => (
        <button key={g.id} type="button" role="tab" aria-selected={group === g.id} onClick={() => onGroup(g.id)}
          className={cn("rounded-md px-3 py-1.5 text-[13.5px]", group === g.id ? "bg-card font-medium shadow-sm" : "text-ink-soft")}
          data-testid={`petitions-tab-${g.id}`}>
          {g.label}
        </button>
      ))}
    </div>
  );
}

function Listing({ page, group, now }: { page: PetitionPage; group: PetitionGroup; now: number }) {
  if (page.petitions.length === 0) {
    return <p className="py-4 text-[14px] text-ink-soft" data-testid="petitions-empty">{EMPTY[group]}</p>;
  }
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

/** Published petitions, open or closed, and the MCE's record of handling them. */
export function PetitionListPage() {
  const [group, setGroup] = useState<PetitionGroup>("open");
  const [topic, setTopic] = useState("");
  const [offset, setOffset] = useState(0);
  const now = useNow();
  const petitions = usePetitions({ group, topic, limit: PAGE, offset });
  const choose = (next: PetitionGroup) => { setGroup(next); setOffset(0); };
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-6">
      <PageIntro eyebrow="Petitions" title="Ask the Assembly to act">
        Residents asking the Accra Metropolitan Assembly to do something, and the support each has gathered. The MCE
        reviews each petition first, and has to decide within 72 hours or it publishes automatically.
      </PageIntro>
      <div className="flex flex-wrap gap-2">
        <Button asChild><Link href="/petitions/new" data-testid="petitions-start">Start a petition</Link></Button>
        <Button asChild variant="secondary"><Link href="/petitions/mine" data-testid="petitions-mine">Your petitions</Link></Button>
      </div>
      {petitions.error ? <ErrorPanel message={petitions.error.message} onRetry={() => void petitions.refetch()} /> : null}
      {petitions.data ? <ModerationRecord moderation={petitions.data.moderation} /> : null}
      <section className="flex flex-col gap-3 rounded-xl border bg-card p-5" aria-label="Petitions">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Tabs group={group} onGroup={choose} />
          <NativeSelect value={topic} onChange={(e) => { setTopic(e.target.value); setOffset(0); }} aria-label="Topic" size="sm" data-testid="petitions-topic">
            <NativeSelectOption value="">All topics</NativeSelectOption>
            {petitions.data?.topics.map((t) => <NativeSelectOption key={t.id} value={t.id}>{t.name}</NativeSelectOption>)}
          </NativeSelect>
        </div>
        {petitions.isPending ? <LoadingPanel label="Loading petitions…" /> : null}
        {petitions.data ? <Listing page={petitions.data} group={group} now={now} /> : null}
        {petitions.data ? <Paging total={petitions.data.total} offset={offset} onOffset={setOffset} /> : null}
      </section>
    </div>
  );
}
