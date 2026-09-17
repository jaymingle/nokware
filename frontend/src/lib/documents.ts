import { deadlineFrom } from "@/lib/time";

import type { DocumentOut } from "@/lib/api/types";

/** Whether a document's clock is still running, so someone can still act on it. */
export function clockRunning(doc: DocumentOut, now: number): boolean {
  return !doc.held_until || deadlineFrom(doc.held_until, now).urgency !== "passed";
}

type ClockSplit = { open: DocumentOut[]; closed: DocumentOut[] };

/**
 * Documents split by whether their clock is still running. Closed ones are
 * publishing automatically: nobody can act on them, so they sit apart.
 */
export function splitByClock(documents: DocumentOut[], now: number): ClockSplit {
  return {
    open: documents.filter((doc) => clockRunning(doc, now)),
    closed: documents.filter((doc) => !clockRunning(doc, now)),
  };
}

/** Held documents split by whether their review window is open. */
export function splitHeld(documents: DocumentOut[], now: number): ClockSplit {
  return splitByClock(
    documents.filter((doc) => doc.status === "held"),
    now,
  );
}

export type Tone = "teal" | "gold" | "brick" | "neutral";

/** Where a submission stands, from the contributor's side. */
type SubmissionView = {
  tone: Tone;
  label: string;
  detail?: string;
  /** A running clock: it publishes automatically unless this happens. */
  clock?: { heldUntil: string; unless: string };
};

function heldView(doc: DocumentOut, department: string, now: number): SubmissionView {
  if (!clockRunning(doc, now)) return { tone: "gold", label: "Publishing now", detail: "No dispute came in time." };
  return {
    tone: "gold",
    label: `With ${department}`,
    detail: doc.resubmission_count > 0 ? "Resubmitted after a dispute." : undefined,
    clock: doc.held_until ? { heldUntil: doc.held_until, unless: `${department} disputes it` } : undefined,
  };
}

function disputedView(doc: DocumentOut, department: string, now: number): SubmissionView {
  if (!doc.escalated_to_mce) return { tone: "brick", label: "Your response needed", detail: `Disputed by ${department}.` };
  if (!clockRunning(doc, now)) return { tone: "gold", label: "Publishing now", detail: "The MCE didn't rule in time." };
  return {
    tone: "gold",
    label: "With the MCE",
    clock: doc.held_until ? { heldUntil: doc.held_until, unless: "the MCE upholds the dispute" } : undefined,
  };
}

export function describeSubmission(doc: DocumentOut, now: number): SubmissionView {
  const department = doc.department_name ?? "the department";
  if (doc.status === "held") return heldView(doc, department, now);
  if (doc.status === "disputed") return disputedView(doc, department, now);
  if (doc.status === "published") return { tone: "teal", label: "Published" };
  const why = doc.escalated_to_mce ? "The MCE upheld the dispute." : "You accepted the dispute.";
  return { tone: "neutral", label: "Withdrawn", detail: why };
}

/**
 * Whether any document's clock has run out while it still shows as held or
 * escalated: the deadline job is about to publish it, so views poll faster.
 */
export function anyPublishingNow(documents: DocumentOut[] | undefined, now: number): boolean {
  return (documents ?? []).some(
    (doc) => (doc.status === "held" || (doc.status === "disputed" && doc.escalated_to_mce)) && !clockRunning(doc, now),
  );
}

/** Disputes waiting on the contributor: they have no clock, so nothing moves until they act. */
export function awaitingResponse(documents: DocumentOut[]): DocumentOut[] {
  return documents.filter((doc) => doc.status === "disputed" && !doc.escalated_to_mce);
}
