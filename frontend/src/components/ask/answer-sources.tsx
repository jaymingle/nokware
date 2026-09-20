"use client";

import { ChevronRightIcon } from "lucide-react";

import { LedgerPdfLink } from "@/components/ask/ledger-pdf-link";
import { SourceCard } from "@/components/ask/source-card";

import type { SourceDocument } from "@/lib/ask/sources";

const SUMMARY = "flex w-fit cursor-pointer list-none items-center gap-1 text-[13px] text-ink-soft hover:text-ink [&::-webkit-details-marker]:hidden";

function Uncited({ documents, testIdPrefix }: { documents: SourceDocument[]; testIdPrefix: string }) {
  const one = documents.length === 1;
  return (
    <details className="group mt-1">
      <summary className={SUMMARY} data-testid={`${testIdPrefix}-uncited-toggle`}>
        <ChevronRightIcon aria-hidden className="size-3.5 transition-transform group-open:rotate-90" />
        {documents.length} other {one ? "document was" : "documents were"} searched but not used in the answer
      </summary>
      <ul className="mt-2 flex flex-col divide-y rounded-lg border bg-card">
        {documents.map((doc) => (
          <li key={doc.label} className="flex flex-wrap items-center justify-between gap-2 px-3.5 py-2.5">
            <div className="min-w-0">
              <p className="text-[14px] break-words">{doc.title}</p>
              <p className="text-[12px] text-ink-soft">{[doc.departmentName, doc.documentYear].filter(Boolean).join(" · ")}</p>
            </div>
            <LedgerPdfLink documentId={doc.documentId} testId={`${testIdPrefix}-uncited-${doc.label}-pdf`} />
          </li>
        ))}
      </ul>
    </details>
  );
}

type AnswerSourcesProps = {
  cited: SourceDocument[];
  uncited: SourceDocument[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  anchorFor: (label: string) => string;
  highlighted: string | null;
  testIdPrefix: string;
};

/** Folded away by default, and opened by the answer's own marks: a citation is how most people get in here. */
export function AnswerSources({ cited, uncited, open, onOpenChange, anchorFor, highlighted, testIdPrefix }: AnswerSourcesProps) {
  return (
    <section aria-label="Sources" className="flex flex-col gap-2">
      {cited.length > 0 ? (
        <details className="group" open={open} onToggle={(event) => onOpenChange(event.currentTarget.open)}>
          <summary className={SUMMARY} data-testid={`${testIdPrefix}-sources-toggle`}>
            <ChevronRightIcon aria-hidden className="size-3.5 transition-transform group-open:rotate-90" />
            Sources ({cited.length})
          </summary>
          <ul className="mt-2 flex flex-col divide-y overflow-hidden rounded-lg border bg-card">
            {cited.map((doc) => (
              <li key={doc.label}>
                <SourceCard doc={doc} anchorId={anchorFor(doc.label)} highlighted={highlighted === doc.label} testIdPrefix={testIdPrefix} />
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {uncited.length > 0 ? <Uncited documents={uncited} testIdPrefix={testIdPrefix} /> : null}
    </section>
  );
}
