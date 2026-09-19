import { CircleCheckIcon, CircleDashedIcon, CircleDotIcon, CircleMinusIcon, TriangleAlertIcon, type LucideIcon } from "lucide-react";

import { ingestionStatus } from "@/lib/status";
import { cn } from "@/lib/utils";

import type { IngestionState } from "@/lib/api/types";
import type { StatusTone } from "@/lib/status";
import type { ReactNode } from "react";

/**
 * The five tones of the status language, and the only place they become colours. Which state takes which tone is
 * decided once, in `@/lib/status`.
 *
 * Colour is never the whole message. Every tag carries its words, and each tone carries its own shape — a dashed
 * ring, a turning dot, a triangle, a tick, a struck-out circle — so the five stay apart in greyscale, in a
 * photocopy, and for a reader who sees no difference between the teal and the brick.
 *
 * The app has one light theme. Each pairing is at least 4.5:1 for its text: ink on the gold tint (gold's own
 * text is under 4.5:1 at this size), teal on its tint at 5.2:1, brick on its tint at 6.8:1, paper on solid teal
 * at 5.5:1, and ink-soft at 6.6:1 for the outlined one. The bare marks meet 3:1 as non-text.
 */
const TONES: Record<StatusTone, { icon: LucideIcon; chip: string; mark: string }> = {
  waiting: { icon: CircleDashedIcon, chip: "border-gold/40 bg-gold-tint text-ink", mark: "text-gold" },
  active: { icon: CircleDotIcon, chip: "border-teal/30 bg-teal-tint text-teal", mark: "text-teal" },
  attention: { icon: TriangleAlertIcon, chip: "border-brick/35 bg-brick-tint text-brick", mark: "text-brick" },
  done: { icon: CircleCheckIcon, chip: "border-teal bg-teal text-paper", mark: "text-teal" },
  ended: { icon: CircleMinusIcon, chip: "border-hairline bg-transparent text-ink-soft", mark: "text-ink-soft" },
};

type StatusTagProps = { tone: StatusTone; children: ReactNode; testId?: string; wrap?: boolean };

/** `wrap` lets a sentence-long label wrap within a narrow column. */
export function StatusTag({ tone, children, testId, wrap = false }: StatusTagProps) {
  const { icon: Icon, chip } = TONES[tone] ?? TONES.waiting;
  return (
    <span
      data-testid={testId}
      data-tone={tone}
      className={cn(
        "inline-flex rounded-lg border px-2.5 py-1 text-[12.5px]",
        wrap ? "max-w-full items-start gap-2 whitespace-normal" : "items-center gap-[7px] whitespace-nowrap",
        chip,
      )}
    >
      <Icon aria-hidden className={cn("size-3.5 shrink-0", wrap && "mt-[3px]")} />
      {children}
    </span>
  );
}

/** Whether a published document can be answered in Ask: the same tag, in the same language, in both libraries. */
export function IngestionTag({ state, testId }: { state: IngestionState; testId?: string }) {
  const { tone, label } = ingestionStatus(state);
  return <StatusTag tone={tone} testId={testId}>{label}</StatusTag>;
}

/** The tone's shape on its own: a step in a trail, or a cell in the publishing record, beside its own words. */
export function StatusMark({ tone, className }: { tone: StatusTone; className?: string }) {
  const { icon: Icon, mark } = TONES[tone] ?? TONES.waiting;
  return <Icon aria-hidden className={cn("size-4 shrink-0", mark, className)} />;
}
