"use client";

import { ChevronRightIcon } from "lucide-react";
import { useState } from "react";

import { LedgerPdfLink } from "@/components/ask/ledger-pdf-link";
import { ProvenanceLine } from "@/components/ask/provenance-line";
import { formatDate } from "@/lib/time";
import { cn } from "@/lib/utils";

import type { SourceDocument } from "@/lib/ask/sources";

function details(doc: SourceDocument): string {
  const year = doc.documentYear ? String(doc.documentYear) : "Year not stated";
  const added = doc.publishedAt ? `Added to the Ledger ${formatDate(doc.publishedAt)}` : null;
  return [doc.departmentName, year, added].filter(Boolean).join(" · ");
}

function Passages({ excerpts, testId }: { excerpts: string[]; testId: string }) {
  return (
    <details className="group">
      <summary
        className="flex w-fit cursor-pointer list-none items-center gap-1 text-[12.5px] text-ink-soft hover:text-ink [&::-webkit-details-marker]:hidden"
        data-testid={testId}
      >
        <ChevronRightIcon aria-hidden className="size-3.5 transition-transform group-open:rotate-90" />
        {excerpts.length === 1 ? "Show the passage used" : `Show the ${excerpts.length} passages used`}
      </summary>
      <div className="mt-2 flex flex-col gap-2">
        {excerpts.map((text, index) => (
          <blockquote key={index} className="border-s-2 border-hairline ps-3 text-[13px] leading-relaxed text-ink-soft">
            {text.replace(/\s+/g, " ").trim()}
          </blockquote>
        ))}
      </div>
    </details>
  );
}

/** What the one line hides: where the document came from, the PDF itself and the passages the answer was read from. */
function Rest({ doc, testId }: { doc: SourceDocument; testId: string }) {
  return (
    <div className="flex flex-col gap-2 px-3.5 pb-3 ps-11">
      <ProvenanceLine provenance={doc.provenance} departmentName={doc.departmentName} sourceUrl={doc.sourceUrl} testId={`${testId}-provenance`} />
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <LedgerPdfLink documentId={doc.documentId} testId={`${testId}-pdf`} />
        <Passages excerpts={doc.excerpts} testId={`${testId}-passages`} />
      </div>
    </div>
  );
}

type SourceCardProps = { doc: SourceDocument; anchorId: string; highlighted: boolean; testIdPrefix: string };

/** One line: the mark used in the answer, the title, and who published it when. The rest opens under it. */
export function SourceCard({ doc, anchorId, highlighted, testIdPrefix }: SourceCardProps) {
  const testId = `${testIdPrefix}-source-${doc.label}`;
  const number = doc.label.replace(/^S/, "");
  const [open, setOpen] = useState(false);
  // A citation followed into a source opens it: the passage it was read from is the point of following it.
  const [jumped, setJumped] = useState(highlighted);
  if (highlighted !== jumped) {
    setJumped(highlighted);
    if (highlighted) setOpen(true);
  }
  return (
    <article id={anchorId} tabIndex={-1} data-testid={testId} data-highlighted={highlighted || undefined}
      className={cn("scroll-mt-6 transition-colors duration-300 outline-none", highlighted && "bg-teal-tint")}>
      <button type="button" aria-expanded={open} onClick={() => setOpen(!open)} data-testid={`${testId}-toggle`}
        className="flex w-full cursor-pointer items-center gap-2.5 px-3.5 py-2.5 text-start">
        <span aria-hidden className={cn("grid h-6 min-w-6 shrink-0 place-items-center rounded-md px-1.5 text-[12px] font-medium tabular-nums transition-colors",
          highlighted ? "bg-teal text-paper" : "bg-teal-tint text-teal")}>
          {number}
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-0.5 sm:flex-row sm:items-baseline sm:gap-2">
          <span className="truncate text-[14.5px] text-ink">
            <span className="sr-only">Source {number}: </span>
            {doc.title}
          </span>
          <span className="truncate text-[12.5px] text-ink-soft">{details(doc)}</span>
        </span>
        <ChevronRightIcon aria-hidden className={cn("size-3.5 shrink-0 text-ink-soft transition-transform", open && "rotate-90")} />
      </button>
      {open ? <Rest doc={doc} testId={testId} /> : null}
    </article>
  );
}
