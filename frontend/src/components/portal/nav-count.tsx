"use client";

import { useNow } from "@/hooks/use-now";
import { useEscalations, useReviewQueue, useSubmissions } from "@/lib/api/queries";
import { awaitingResponse, splitByClock, splitHeld } from "@/lib/documents";
import { cn } from "@/lib/utils";

import type { NavCountKind } from "@/lib/portal/navigation";

function Count({ value, active, testId }: { value: number; active: boolean; testId: string }) {
  if (value === 0) return null;
  return (
    <span
      data-testid={testId}
      aria-label={`${value} waiting`}
      className={cn(
        "ml-1.5 inline-grid min-w-5 place-items-center rounded-md px-1 text-[11.5px] font-medium tabular-nums",
        active ? "bg-teal text-paper" : "bg-gold-tint text-ink",
      )}
    >
      {value}
    </span>
  );
}

/** Documents this department can still review: each will publish on its own. */
function ReviewCount({ active }: { active: boolean }) {
  const now = useNow();
  const { data } = useReviewQueue();
  const open = data ? splitHeld(data, now).open.length : 0;
  return <Count value={open} active={active} testId="nav-count-review" />;
}

/** Disputes waiting on this contributor, which don't move until they respond. */
function ResponsesCount({ active }: { active: boolean }) {
  const { data } = useSubmissions();
  return <Count value={data ? awaitingResponse(data).length : 0} active={active} testId="nav-count-responses" />;
}

/** Escalated disputes the MCE can still rule on: each will publish on its own. */
function EscalationsCount({ active }: { active: boolean }) {
  const now = useNow();
  const { data } = useEscalations();
  const open = data ? splitByClock(data, now).open.length : 0;
  return <Count value={open} active={active} testId="nav-count-escalations" />;
}

export function NavCount({ kind, active }: { kind: NavCountKind; active: boolean }) {
  if (kind === "review") return <ReviewCount active={active} />;
  if (kind === "responses") return <ResponsesCount active={active} />;
  if (kind === "escalations") return <EscalationsCount active={active} />;
  return null;
}
