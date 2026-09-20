"use client";

import { useState, type ReactNode } from "react";

import { ContactItem } from "@/components/contacts/contact-item";
import { ErrorNote } from "@/components/documents/panels";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useRepresentatives } from "@/lib/api/public-queries";
import { matchAreas, type AreaMatch } from "@/lib/areas";
import { cn } from "@/lib/utils";

import type { Representation } from "@/lib/api/types";

function Fact({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid gap-0.5 sm:grid-cols-[9.5rem_1fr] sm:gap-3">
      <dt className="text-[12.5px] text-ink-soft sm:pt-0.5">{label}</dt>
      <dd className="text-[14.5px]">{children}</dd>
    </div>
  );
}

function Representative({ match, data }: { match: AreaMatch; data: Representation }) {
  const { area, subMetro, spelledAs } = match;
  return (
    <div className="flex flex-col gap-4 rounded-xl border bg-card p-4 sm:p-5" data-testid="representative">
      <p className="text-[16px]">
        <strong className="font-medium">{area.name}</strong>
        {spelledAs ? <span className="text-ink-soft"> (also spelled {spelledAs})</span> : null} is in the{" "}
        <strong className="font-medium">{subMetro.name}</strong> sub-metro.
      </p>
      <dl className="flex flex-col gap-3">
        <Fact label="Chairperson">
          {subMetro.chairperson}, Assembly Member for {subMetro.chairperson_area}
        </Fact>
        <Fact label="Sub-metro office">{subMetro.office}</Fact>
        <Fact label="How to reach it">
          No direct line for the sub-metro office is published. Call the Assembly&apos;s switchboard and ask for the{" "}
          {subMetro.name} sub-metro office.
        </Fact>
      </dl>
      <ul>
        <ContactItem contact={data.switchboard} />
      </ul>
      {area.note ? <p className="text-[12.5px] text-ink-soft">{area.note}</p> : null}
      <p className="text-[12px] text-ink-soft">
        Sub-metro, chairperson and office:{" "}
        <a href={data.source.url} target="_blank" rel="noopener" className="text-teal underline underline-offset-2" data-testid="representative-source">
          {data.source.label}
        </a>
      </p>
    </div>
  );
}

function AreaChoices({ matches, chosen, onChoose }: { matches: AreaMatch[]; chosen: string | null; onChoose: (id: string) => void }) {
  if (matches.length === 0) return <ErrorNote testId="area-none">No electoral area by that name. Check the spelling, or clear the box to see them all.</ErrorNote>;
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Electoral areas">
      {matches.map(({ area }) => (
        <li key={area.id}>
          <button
            type="button"
            onClick={() => onChoose(area.id)}
            aria-pressed={chosen === area.id}
            className={cn("rounded-lg border px-3 py-1.5 text-[13.5px] transition-colors hover:border-teal", chosen === area.id ? "border-teal bg-teal-tint text-teal" : "bg-card")}
            data-testid={`area-${area.id}`}
          >
            {area.name}
          </button>
        </li>
      ))}
    </ul>
  );
}

export function WhoRepresentsYou() {
  const { data, error } = useRepresentatives();
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<string | null>(null);
  const matches = data ? matchAreas(query, data.sub_metros) : [];
  const match = matches.find((m) => m.area.id === chosen);
  return (
    <section id="who-represents-you" aria-labelledby="who-represents-you-title" className="flex flex-col gap-3">
      <h2 id="who-represents-you-title" className="text-[21px]">Who represents you</h2>
      <p className="max-w-[62ch] text-[14px] text-ink-soft">
        Choose your electoral area to see its sub-metro, the sub-metro&apos;s chairperson and where its office is.
      </p>
      {error ? <ErrorNote>{error.message}</ErrorNote> : null}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="area-search">Your electoral area</Label>
        <Input id="area-search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Type to narrow the list, e.g. Kinka" autoComplete="off" className="max-w-80" data-testid="area-search" />
      </div>
      {data ? <AreaChoices matches={matches} chosen={chosen} onChoose={setChosen} /> : null}
      {data && match ? <Representative match={match} data={data} /> : null}
    </section>
  );
}
