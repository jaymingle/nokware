"use client";

import { FileTextIcon } from "lucide-react";

import { ledgerFileUrl } from "@/lib/api/public";
import { describeProvenance } from "@/lib/ask/sources";
import { LEDGER_NOTE } from "@/lib/petitions";

import type { LedgerMatch, PetitionDocument } from "@/lib/api/types";

/** Title (opening the PDF), then who published it and when, as Ask says it. */
export function DocumentLine({ doc }: { doc: PetitionDocument }) {
  const provenance = describeProvenance({ provenance: doc.provenance, departmentName: doc.department_name, sourceUrl: null });
  const meta = [provenance?.text, doc.year ? String(doc.year) : null].filter(Boolean).join(" · ");
  return (
    <div className="flex min-w-0 flex-col gap-0.5">
      <a href={ledgerFileUrl(doc.id)} target="_blank" rel="noopener noreferrer"
        className="inline-flex items-start gap-1.5 text-[14px] font-medium text-teal underline underline-offset-2" data-testid={`ledger-doc-${doc.id}`}>
        <FileTextIcon aria-hidden className="mt-0.5 size-3.5 shrink-0" />
        {doc.title}
      </a>
      {meta ? <p className="text-[12px] text-ink-soft">{meta}</p> : null}
    </div>
  );
}

type Cite = { chosen: Set<string>; toggle: (id: string) => void; full: boolean };

function Match({ match, cite }: { match: LedgerMatch; cite?: Cite }) {
  const checked = cite?.chosen.has(match.id) ?? false;
  return (
    <li className="flex flex-col gap-2 border-b py-3 last:border-0" data-testid={`ledger-match-${match.id}`}>
      <DocumentLine doc={match} />
      <blockquote className="border-l-2 border-hairline pl-3 text-[13px] text-ink-soft">{match.passage}</blockquote>
      {cite ? (
        <label className="flex items-center gap-2 text-[13px]">
          <input type="checkbox" checked={checked} disabled={!checked && cite.full} onChange={() => cite.toggle(match.id)}
            className="size-4 accent-teal" data-testid={`ledger-cite-${match.id}`} />
          Cite this in the petition
        </label>
      ) : null}
    </li>
  );
}

/** What the Ledger already holds on a petition's subject, with how it was found and what a match does and doesn't mean. */
export function LedgerMatches({ matches, cite, testId }: { matches: LedgerMatch[]; cite?: Cite; testId: string }) {
  return (
    <div className="flex flex-col gap-2" data-testid={testId}>
      <p className="text-[12.5px] text-ink-soft">{LEDGER_NOTE}</p>
      {matches.length === 0 ? (
        <p className="py-2 text-[13.5px] text-ink-soft">Nothing in The Ledger matched this petition&apos;s words.</p>
      ) : (
        <ul>{matches.map((match) => <Match key={match.id} match={match} cite={cite} />)}</ul>
      )}
    </div>
  );
}
