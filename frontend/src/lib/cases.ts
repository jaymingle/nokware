import type { CaseSummary } from "@/lib/api/types";
import type { Tone } from "@/lib/documents";

const HOUR_MS = 3_600_000;
const DAY_MS = 24 * HOUR_MS;

const STATUS: Record<string, [Tone, string]> = {
  submitted: ["gold", "Awaiting routing"],
  assigned: ["gold", "New"],
  in_progress: ["teal", "In progress"],
  resolved: ["neutral", "Resolved"],
  escalated: ["brick", "Escalated"],
};

/** The tag for a case, from the caller's side: their own part, if they have one. */
export function caseStatusTag(summary: Pick<CaseSummary, "status" | "my_status">): { tone: Tone; label: string } {
  if (summary.status === "escalated") return { tone: "brick", label: "Escalated to the MCE" };
  const [tone, label] = STATUS[summary.my_status ?? summary.status] ?? ["neutral", summary.status];
  return { tone, label };
}

export function caseAge(submittedAt: string, now: number): string {
  const elapsed = Math.max(0, now - Date.parse(submittedAt));
  if (elapsed < HOUR_MS) return "<1h";
  if (elapsed < DAY_MS) return `${Math.floor(elapsed / HOUR_MS)}h`;
  return `${Math.floor(elapsed / DAY_MS)}d`;
}

export function openForMe(cases: CaseSummary[]): number {
  return cases.filter((c) => c.allowed_actions.length > 0).length;
}

export const SEVERITY_LABELS: Record<number, string> = {
  1: "Minor",
  2: "Nuisance",
  3: "Affects a community",
  4: "Risk of harm",
  5: "Immediate danger",
};

const EVENT_LABELS: Record<string, string> = {
  submitted: "Reported by a resident",
  classified: "Filed",
  assigned: "Routed",
  acknowledged: "Work started",
  resolved: "Resolved",
  escalated: "Escalated to the MCE",
  reassigned: "Reassigned",
  escalation_confirmed: "The MCE confirmed the resolution",
  reclassified: "Refiled",
  notified: "Message to the citizen",
  contact_deleted: "The citizen's numbers were deleted",
  location_shared: "The citizen shared a precise location",
  location_viewed: "The shared location was viewed",
  location_removed: "The citizen removed the location they shared",
};

export function caseEventText(event: { action: string; note?: string | null }): string {
  return event.note ?? EVENT_LABELS[event.action] ?? event.action;
}
