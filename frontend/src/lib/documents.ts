import { deadlineFrom } from "@/lib/time";

import type { DocumentOut } from "@/lib/api/types";

/** Whether a document's clock is still running, so someone can still act on it. */
export function clockRunning(doc: DocumentOut, now: number): boolean {
  return !doc.held_until || deadlineFrom(doc.held_until, now).urgency !== "passed";
}

/**
 * Held documents split by whether their review window is open. Closed ones are
 * publishing automatically: nobody can act on them, so they sit apart.
 */
export function splitHeld(documents: DocumentOut[], now: number): { open: DocumentOut[]; closed: DocumentOut[] } {
  const held = documents.filter((doc) => doc.status === "held");
  return {
    open: held.filter((doc) => clockRunning(doc, now)),
    closed: held.filter((doc) => !clockRunning(doc, now)),
  };
}
