import { ExternalLinkIcon } from "lucide-react";

import type { DocumentOut } from "@/lib/api/types";

function sourceHost(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

export function DocumentSummary({ doc, byline }: { doc: DocumentOut; byline: string }) {
  const details = [doc.category, doc.document_year, byline].filter(Boolean).join(" · ");
  return (
    <div className="flex flex-col gap-1.5">
      <h3 className="text-[20px] leading-snug">{doc.title}</h3>
      <p className="text-[12.5px] text-ink-soft">{details}</p>
      {doc.source_url ? (
        <a
          href={doc.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex w-fit items-center gap-1 text-[12.5px] text-teal underline underline-offset-2"
          data-testid={`source-link-${doc.id}`}
        >
          Source: {sourceHost(doc.source_url)}
          <ExternalLinkIcon aria-hidden className="size-3" />
        </a>
      ) : null}
    </div>
  );
}
