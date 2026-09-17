import { ChevronRightIcon } from "lucide-react";

import { LedgerPdfLink } from "@/components/ask/ledger-pdf-link";
import { SourceCard } from "@/components/ask/source-card";

import type { SourceDocument } from "@/lib/ask/sources";

function Uncited({ documents, testIdPrefix }: { documents: SourceDocument[]; testIdPrefix: string }) {
  const one = documents.length === 1;
  return (
    <details className="group mt-1">
      <summary
        className="flex w-fit cursor-pointer list-none items-center gap-1 text-[13px] text-ink-soft hover:text-ink [&::-webkit-details-marker]:hidden"
        data-testid={`${testIdPrefix}-uncited-toggle`}
      >
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
  anchorFor: (label: string) => string;
  highlighted: string | null;
  testIdPrefix: string;
};

export function AnswerSources({ cited, uncited, anchorFor, highlighted, testIdPrefix }: AnswerSourcesProps) {
  return (
    <section aria-label="Sources" className="flex flex-col gap-2.5">
      {cited.length > 0 ? <h3 className="font-sans text-[12px] font-medium tracking-wide text-ink-soft uppercase">Sources</h3> : null}
      {cited.map((doc) => (
        <SourceCard key={doc.label} doc={doc} anchorId={anchorFor(doc.label)} highlighted={highlighted === doc.label} testIdPrefix={testIdPrefix} />
      ))}
      {uncited.length > 0 ? <Uncited documents={uncited} testIdPrefix={testIdPrefix} /> : null}
    </section>
  );
}
