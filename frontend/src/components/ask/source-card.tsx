import { ChevronRightIcon } from "lucide-react";

import { LedgerPdfLink } from "@/components/ask/ledger-pdf-link";
import { ProvenanceLine } from "@/components/ask/provenance-line";
import { cn } from "@/lib/utils";
import { formatDate } from "@/lib/time";

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

type SourceCardProps = { doc: SourceDocument; anchorId: string; highlighted: boolean; testIdPrefix: string };

/** A cited document, numbered like the tags in the answer, with where it came from. */
export function SourceCard({ doc, anchorId, highlighted, testIdPrefix }: SourceCardProps) {
  const testId = `${testIdPrefix}-source-${doc.label}`;
  return (
    <article
      id={anchorId}
      tabIndex={-1}
      data-testid={testId}
      data-highlighted={highlighted || undefined}
      className={cn(
        "flex scroll-mt-6 gap-3 rounded-lg border bg-card p-3.5 transition-[box-shadow,border-color] duration-300 outline-none",
        highlighted && "border-teal bg-teal-tint/40 ring-2 ring-teal/50",
      )}
    >
      <span aria-hidden className="grid h-6 min-w-6 shrink-0 place-items-center rounded-md bg-teal-tint px-1.5 text-[12px] font-medium text-teal tabular-nums">
        {doc.label.replace(/^S/, "")}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <h3 className="text-[15.5px] leading-snug break-words">
          <span className="sr-only">Source {doc.label.replace(/^S/, "")}: </span>
          {doc.title}
        </h3>
        <p className="text-[12.5px] text-ink-soft">{details(doc)}</p>
        <ProvenanceLine provenance={doc.provenance} departmentName={doc.departmentName} sourceUrl={doc.sourceUrl} testId={`${testId}-provenance`} />
        <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-2">
          <LedgerPdfLink documentId={doc.documentId} testId={`${testId}-pdf`} />
          <Passages excerpts={doc.excerpts} testId={`${testId}-passages`} />
        </div>
      </div>
    </article>
  );
}
