import { cn } from "@/lib/utils";

import type { IngestionState } from "@/lib/api/types";
import type { Tone } from "@/lib/documents";
import type { ReactNode } from "react";

// Gold tags carry ink text: gold on its tint is under 4.5:1 at this size.
const TONES: Record<Tone, string> = {
  teal: "bg-teal-tint text-teal",
  gold: "bg-gold-tint text-ink",
  brick: "bg-brick-tint text-brick",
  neutral: "border text-ink-soft",
};

type TagProps = { tone: Tone; children: ReactNode; testId?: string; wrap?: boolean };

/** `wrap` lets a sentence-long label wrap within a narrow column. */
export function Tag({ tone, children, testId, wrap = false }: TagProps) {
  return (
    <span
      data-testid={testId}
      className={cn(
        "inline-flex items-center gap-[7px] rounded-lg px-2.5 py-1 text-[12.5px]",
        wrap ? "max-w-full whitespace-normal" : "whitespace-nowrap",
        TONES[tone],
      )}
    >
      {children}
    </span>
  );
}

const INGESTION: Record<IngestionState, [Tone, string]> = {
  searchable: ["teal", "Answerable in Ask"],
  processing: ["neutral", "Processing"],
  not_searchable: ["gold", "Scanned, not searchable"],
  failed: ["brick", "Indexing failed, retrying"],
};

export function IngestionTag({ state, testId }: { state: IngestionState; testId?: string }) {
  const [tone, label] = INGESTION[state];
  return (
    <Tag tone={tone} testId={testId}>
      {label}
    </Tag>
  );
}
