"use client";

import { cn } from "@/lib/utils";
import { deadlineFrom } from "@/lib/time";

import type { DocumentOut } from "@/lib/api/types";

type QueueSummaryProps = { open: DocumentOut[]; closed: number; now: number };

/**
 * The review queue's headline: how many documents will publish on their own
 * unless disputed, and when the next one goes. Open documents arrive soonest
 * deadline first.
 */
export function QueueSummary({ open, closed, now }: QueueSummaryProps) {
  const next = open[0]?.held_until;
  if (!next) return null;
  const { label, urgency } = deadlineFrom(next, now);
  const one = open.length === 1;
  return (
    <div
      data-testid="review-summary"
      data-urgency={urgency}
      className={cn(
        "flex flex-wrap items-center gap-x-6 gap-y-3 rounded-xl border px-6 py-5",
        urgency === "urgent" ? "border-brick bg-brick-tint" : "border-gold bg-gold-tint",
      )}
    >
      <span className="font-heading text-[44px] leading-none tabular-nums">{open.length}</span>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p className="text-base font-medium">
          {one ? "document publishes" : "documents publish"} automatically unless you dispute {one ? "it" : "them"}.
        </p>
        <p className="text-[13.5px] text-ink-soft">
          The next one publishes in <span className="font-medium text-ink tabular-nums">{label}</span>. If you do
          nothing, each goes into the public Ledger and Ask under your department&apos;s name when its clock runs out.
          {closed > 0 ? ` ${closed} more ${closed === 1 ? "has" : "have"} run out of time and ${closed === 1 ? "is" : "are"} being published.` : ""}
        </p>
      </div>
    </div>
  );
}
