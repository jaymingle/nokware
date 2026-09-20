import type { CaseDetail, CaseEvent, CaseSummary } from "@/lib/api/types";

const HOUR_MS = 3_600_000;
const DAY_MS = 24 * HOUR_MS;

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
  reopened: "The MCE sent it back to be finished",
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

const INTERNAL_LABEL = "Internal: not shown to the resident";

/**
 * The field a stage's note is written in. On an everyday case the note is written for the resident and appears on
 * their status page; on a personal-safety case that page carries fixed lines only, so the note stays internal.
 */
export function caseNoteCopy(isPrivate: boolean): { label: string; hint: string } {
  if (isPrivate) {
    return { label: INTERNAL_LABEL, hint: "It stays in the audit trail with your name. The resident's status page says only how far the case has got." };
  }
  return {
    label: "The resident will see this note",
    hint: "Say what was done or what happens next. Don't include names, phone numbers or addresses.",
  };
}

/** Said beside a note in the trail, so staff can see at a glance who reads it. */
export function caseNoteReader(internal: boolean): string {
  return internal ? INTERNAL_LABEL : "The resident reads this note";
}

export type TrailStep = {
  event: CaseEvent;
  /** Whether the resident sees this step on their status page. */
  seen: boolean;
  /** What staff wrote at this step, when they wrote anything. */
  note: string | null;
  /** Whether that note is kept from the resident. */
  internal: boolean;
};

/**
 * The trail in the order it happened, marked with what the resident reads of it.
 *
 * Which steps those are is the API's answer (`seen_by_the_resident`), not a rule kept here: a second copy would
 * go on saying "the resident reads this" long after the server stopped showing it.
 */
export function caseTrail(detail: Pick<CaseDetail, "private" | "history">): TrailStep[] {
  return detail.history.map((event) => ({
    event,
    seen: event.seen_by_the_resident,
    note: event.staff_note,
    internal: detail.private,
  }));
}

/** What a department sees its own part of a case as: the MCE's view of the whole case is filtered separately. */
export const MY_FILTERS = {
  all: { label: "All", matches: () => true },
  new: { label: "New", matches: (c: CaseSummary) => c.my_status === "assigned" && c.status !== "escalated" },
  in_progress: { label: "In progress", matches: (c: CaseSummary) => c.my_status === "in_progress" && c.status !== "escalated" },
  resolved: { label: "Resolved", matches: (c: CaseSummary) => c.my_status === "resolved" || c.status === "resolved" },
} as const;

export type MyFilterKey = keyof typeof MY_FILTERS;

/**
 * The queue arrives unfinished first, then most severe, then longest waiting — so nobody's report is left while
 * newer ones are picked off. Newest first is offered beside it, not instead of it.
 */
export const ORDERS = {
  urgent: { label: "Most urgent", sort: null },
  newest: { label: "Newest first", sort: (a: CaseSummary, b: CaseSummary) => Date.parse(b.submitted_at) - Date.parse(a.submitted_at) },
} as const;

export type OrderKey = keyof typeof ORDERS;

export function arrange(cases: CaseSummary[], filter: MyFilterKey, order: OrderKey): CaseSummary[] {
  const shown = cases.filter(MY_FILTERS[filter].matches);
  const sort = ORDERS[order].sort;
  return sort ? [...shown].sort(sort) : shown;
}
