import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import type { IngestionState } from "@/lib/api/types";

// The design's status tags. Gold tags carry ink text: gold on its tint is
// under 4.5:1 at this size.
const TONES = {
  teal: "bg-teal-tint text-teal",
  gold: "bg-gold-tint text-ink",
  brick: "bg-brick-tint text-brick",
  neutral: "border text-ink-soft",
} as const;

export type TagTone = keyof typeof TONES;

export function Tag({ tone, children, testId }: { tone: TagTone; children: ReactNode; testId?: string }) {
  return (
    <span
      data-testid={testId}
      className={cn("inline-flex items-center gap-[7px] rounded-lg px-2.5 py-1 text-[12.5px] whitespace-nowrap", TONES[tone])}
    >
      {children}
    </span>
  );
}

const INGESTION: Record<IngestionState, [TagTone, string]> = {
  searchable: ["teal", "Answerable in Ask"],
  processing: ["neutral", "Processing"],
  not_searchable: ["gold", "Scanned, not searchable"],
  failed: ["brick", "Indexing failed, retrying"],
};

/** Whether a published document can be found in Ask yet. */
export function IngestionTag({ state, testId }: { state: IngestionState; testId?: string }) {
  const [tone, label] = INGESTION[state];
  return (
    <Tag tone={tone} testId={testId}>
      {label}
    </Tag>
  );
}
