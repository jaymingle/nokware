"use client";

import { deadlineFrom } from "@/lib/time";
import { cn } from "@/lib/utils";

import type { DocumentOut } from "@/lib/api/types";

type ClockSummaryProps = {
  /** Documents whose clock is running, soonest deadline first. */
  open: DocumentOut[];
  /** How many have run out of time and are being published. */
  closed: number;
  now: number;
  /** What stops publication, for one document and for several, e.g. "you dispute it" / "you dispute them". */
  unless: { one: string; many: string };
  /** What silence means for the reader, e.g. whose name the document goes out under. */
  consequence: string;
  testId: string;
};

function closedNote(closed: number): string {
  if (closed === 0) return "";
  const one = closed === 1;
  return ` ${closed} more ${one ? "has" : "have"} run out of time and ${one ? "is" : "are"} being published.`;
}

/**
 * A queue's headline: how many documents will publish on their own unless
 * the reader acts, and when the next one goes.
 */
export function ClockSummary({ open, closed, now, unless, consequence, testId }: ClockSummaryProps) {
  const next = open[0]?.held_until;
  if (!next) return null;
  const { label, urgency } = deadlineFrom(next, now);
  const one = open.length === 1;
  return (
    <div
      data-testid={testId}
      data-urgency={urgency}
      className={cn(
        "flex flex-wrap items-center gap-x-6 gap-y-3 rounded-xl border px-6 py-5",
        urgency === "urgent" ? "border-brick bg-brick-tint" : "border-gold bg-gold-tint",
      )}
    >
      <span className="font-heading text-[44px] leading-none tabular-nums">{open.length}</span>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p className="text-base font-medium">
          {one ? "document publishes" : "documents publish"} automatically unless {one ? unless.one : unless.many}.
        </p>
        <p className="text-[13.5px] text-ink-soft">
          The next one publishes in <span className="font-medium text-ink tabular-nums">{label}</span>. {consequence}
          {closedNote(closed)}
        </p>
      </div>
    </div>
  );
}
