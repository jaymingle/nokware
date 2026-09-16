import { ExternalLinkIcon } from "lucide-react";

import { describeProvenance, type SourceDocument } from "@/lib/ask/sources";

type ProvenanceLineProps = Pick<SourceDocument, "provenance" | "departmentName" | "sourceUrl"> & { testId: string };

/** Where the document came from, e.g. "Published by Finance on ama.gov.gh", with the original linked. */
export function ProvenanceLine({ testId, ...doc }: ProvenanceLineProps) {
  const view = describeProvenance(doc);
  if (!view) return null;
  return (
    <p className="text-[13px] text-ink" data-testid={testId}>
      {view.text}
      {view.link ? (
        <>
          {view.joiner}
          <a
            href={view.link.href}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-0.5 text-teal underline underline-offset-2"
            data-testid={`${testId}-link`}
          >
            {view.link.text}
            <ExternalLinkIcon aria-hidden className="size-3" />
          </a>
        </>
      ) : null}
    </p>
  );
}
