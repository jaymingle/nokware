"use client";

import { useNow } from "@/hooks/use-now";
import { useReviewQueue } from "@/lib/api/queries";
import { splitHeld } from "@/lib/documents";
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

export function NavCount({ kind, active }: { kind: NavCountKind; active: boolean }) {
  if (kind === "review") return <ReviewCount active={active} />;
  return null;
}
