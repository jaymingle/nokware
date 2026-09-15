import { formatDate } from "@/lib/time";

import type { PetitionCard, PetitionStatus, PetitionTimelineEntry, PhoneChallenge } from "@/lib/api/types";

// How a petition reads in public, and what this browser keeps while someone starts one. The MCE is usually a
// petition's target, so the page always says who published it: the MCE, or the clock when the MCE didn't decide.

const DAY_MS = 86_400_000;

export const STATUS_LABELS: Record<PetitionStatus, string> = {
  in_review: "Waiting for the MCE's review",
  refused: "Refused by the MCE",
  open: "Open",
  awaiting_response: "With the MCE for a response",
  responded: "Answered by the MCE",
  closed: "Closed",
  withdrawn: "Withdrawn",
};

export const NAME_NOTE =
  "If you show your name, anyone can see it on the petition, including the department it concerns. If you stay anonymous, you still count; only your name is withheld. You can take your name off later.";

/** The same, naming the department when it is known: who exactly can see a public name. */
export function nameNote(concerns: string | null): string {
  return concerns ? NAME_NOTE.replace("the department it concerns", `${concerns}, which it concerns`) : NAME_NOTE;
}

export const NO_RESPONSE = "No response 30 days after the petition reached its threshold.";

export const LEDGER_NOTE =
  "Found by searching the Assembly's published documents for this petition's words. A match means a document touches the subject, not that it commits to what the petition asks, and the search can miss documents.";

/** A petition number or a code in two threes, "482 913": easier to read aloud and type on a keypad. */
export function spacedCode(code: string): string {
  return `${code.slice(0, 3)} ${code.slice(3)}`;
}

export function placeLine(petition: Pick<PetitionCard, "scope" | "area" | "sub_metro">): string {
  if (petition.scope === "metro") return "The whole Assembly";
  return [petition.area, petition.sub_metro].filter(Boolean).join(", ");
}

export function startedBy(name: string | null): string {
  return name ? `Started by ${name}` : "Started by a resident";
}

/** Who published it: the MCE, or the 72-hour clock the MCE let run out. */
export function publishedLine(petition: Pick<PetitionCard, "published_at" | "published_by">): string | null {
  if (!petition.published_at) return null;
  const on = formatDate(petition.published_at);
  return petition.published_by === "automatic"
    ? `Published automatically on ${on}: the MCE didn't decide within 72 hours`
    : `Published by the MCE on ${on}`;
}

export function signaturesLine(signatures: number, threshold: number | null): string {
  const count = `${signatures.toLocaleString()} ${signatures === 1 ? "signature" : "signatures"}`;
  return threshold ? `${count} of ${threshold.toLocaleString()}` : count;
}

export function progressPercent(signatures: number, threshold: number | null): number {
  return threshold ? Math.min(100, Math.round((signatures / threshold) * 100)) : 0;
}

export function daysLeft(iso: string, now: number): number {
  return Math.max(0, Math.ceil((Date.parse(iso) - now) / DAY_MS));
}

type Standing = Pick<PetitionCard, "status" | "threshold" | "threshold_reached_at" | "response_due" | "responded_at" | "unanswered_at">;

/** When, and how late, the MCE responded: "N days after the 30-day deadline" if it passed first. */
export function respondedLine(petition: Pick<PetitionCard, "responded_at" | "response_due">): string | null {
  if (!petition.responded_at) return null;
  const late = petition.response_due ? Math.ceil((Date.parse(petition.responded_at) - Date.parse(petition.response_due)) / DAY_MS) : 0;
  const lateness = late > 0 ? `, ${late} ${late === 1 ? "day" : "days"} after the 30-day deadline` : "";
  return `The MCE responded on ${formatDate(petition.responded_at)}${lateness}.`;
}

/** Once it reached its threshold: when, and the MCE's 30 days to respond, counted down, then said plainly if they pass. */
export function responseLine(petition: Standing, now: number, where = "on this page"): string | null {
  if (petition.status === "responded") return respondedLine(petition);
  if (petition.status !== "awaiting_response" || !petition.threshold_reached_at || !petition.response_due) return null;
  const reached = `Reached ${petition.threshold?.toLocaleString()} signatures on ${formatDate(petition.threshold_reached_at)}.`;
  const left = daysLeft(petition.response_due, now);
  if (left === 0 || petition.unanswered_at) return `${reached} ${NO_RESPONSE}`;
  return `${reached} The MCE has until ${formatDate(petition.response_due)} to respond publicly ${where}: ${left} ${left === 1 ? "day" : "days"} left.`;
}

/** Where the petition stands in time: open until when, or when and why it closed. */
export function closingLine(petition: Pick<PetitionCard, "status" | "closes_at" | "closed_at" | "threshold">, now: number): string | null {
  if (petition.status === "responded") return "It takes no more signatures: the MCE has responded.";
  if (petition.status === "awaiting_response" && petition.closes_at) {
    return Date.parse(petition.closes_at) > now ? `Signing stays open until ${formatDate(petition.closes_at)}` : "Signing has closed";
  }
  if (petition.status === "open" && petition.closes_at) {
    const left = daysLeft(petition.closes_at, now);
    return `Open until ${formatDate(petition.closes_at)} (${left} ${left === 1 ? "day" : "days"} left)`;
  }
  if (!petition.closed_at) return null;
  if (petition.status === "withdrawn") return `Withdrawn by the person who started it on ${formatDate(petition.closed_at)}`;
  const goal = petition.threshold ? ` It didn't reach ${petition.threshold.toLocaleString()} signatures in 90 days.` : "";
  return `Closed on ${formatDate(petition.closed_at)}.${goal}`;
}

const TIMELINE: Record<PetitionTimelineEntry["action"], string> = {
  submitted: "Sent to the MCE for review",
  resubmitted: "Edited and sent back for review",
  published: "Published by the MCE",
  auto_published: "Published automatically: the MCE didn't decide within 72 hours",
  refused: "Refused by the MCE",
  withdrawn: "Withdrawn by the person who started it",
  closed: "Closed after 90 days",
  threshold_reached: "Reached its signatures and went to the MCE for a response",
  responded: "The MCE responded",
  no_response: "No response 30 days after the petition reached its threshold",
};

export function timelineText(entry: PetitionTimelineEntry): string {
  return entry.reason ? `${TIMELINE[entry.action]}: ${entry.reason}` : TIMELINE[entry.action];
}

/** A WhatsApp share link carrying the ask and the page's address. */
export function whatsappShareUrl(title: string, pageUrl: string): string {
  return `https://wa.me/?text=${encodeURIComponent(`Petition to the Accra Metropolitan Assembly: ${title}\n${pageUrl}`)}`;
}

// What this browser keeps. The proof of a confirmed phone lives in this tab only (sessionStorage), so a shared
// computer forgets it when the tab closes; the server refuses it after 12 hours anyway. The draft is kept so
// switching to WhatsApp to confirm, or reloading, loses nothing.

const PROOF_KEY = "nokware-phone-proof";
const CHALLENGE_KEY = "nokware-phone-challenge";
const DRAFT_KEY = "nokware-petition-draft";

export type KeptProof = { token: string; number: string; expiresAt: string };
export type KeptChallenge = PhoneChallenge & { startedAt: number };

function read<T>(storage: () => Storage, key: string): T | null {
  try {
    const raw = storage().getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function write(storage: () => Storage, key: string, value: unknown): void {
  try {
    if (value === null) storage().removeItem(key);
    else storage().setItem(key, JSON.stringify(value));
  } catch {
    // Storage off (a private window): the page still works, it just won't remember.
  }
}

const session = () => sessionStorage;
const local = () => localStorage;

export function keptProof(now: number): KeptProof | null {
  const proof = read<KeptProof>(session, PROOF_KEY);
  return proof && Date.parse(proof.expiresAt) > now ? proof : null;
}

export const keepProof = (proof: KeptProof | null) => write(session, PROOF_KEY, proof);

export function keptChallenge(now: number): KeptChallenge | null {
  const challenge = read<KeptChallenge>(session, CHALLENGE_KEY);
  return challenge && now < challenge.startedAt + challenge.expires_in * 1000 ? challenge : null;
}

export const keepChallenge = (challenge: KeptChallenge | null) => write(session, CHALLENGE_KEY, challenge);

export function keptDraft<T>(): T | null {
  return read<T>(local, DRAFT_KEY);
}
export const keepDraft = (draft: unknown) => write(local, DRAFT_KEY, draft);
