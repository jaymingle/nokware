import { formatDate } from "@/lib/time";

import type { PetitionGroup } from "@/lib/api/petitions";
import type {
  Option, PetitionDepartmentShare, PetitionGround, PetitionGroundOption, PetitionPage, PetitionStatus, SharedPetition,
} from "@/lib/api/types";

/**
 * The portal's side of petitions. Nobody in here approves one: a contributor takes a petition down on a named
 * ground, and the MCE reads and answers. The grounds and the dismissal reasons are never written out in a
 * component — they arrive with the reports queue, in the same words the public report form and the tombstone use.
 */

/** Said before a removal is sent, and nowhere else. A removal is undone by the creator, not by a contributor. */
export const REMOVAL_CONFIRMATION =
  "This replaces the petition with a notice giving this ground. The creator can fix it and republish.";

export function groundById(grounds: PetitionGroundOption[], id: PetitionGround | ""): PetitionGroundOption | undefined {
  return grounds.find((ground) => ground.id === id);
}

/**
 * The MCE's queue is filed under the states a petition can stand in. Four of them the API lists petitions for;
 * "removed" lists none — a removed petition is in no group, and only its number opens its notice — so that chip
 * shows the removal record instead.
 */
export type PortalPetitionGroup = PetitionGroup | "removed";

/** The same order, and the same five tabs, as the public petitions list. */
export const PORTAL_GROUPS: PortalPetitionGroup[] = ["open", "awaiting", "responded", "removed", "closed"];

/** Each group's state, so a chip can be labelled in the server's own status words rather than this file's. */
export const GROUP_STATUS: Record<PortalPetitionGroup, PetitionStatus> = {
  open: "open",
  awaiting: "awaiting_response",
  responded: "responded",
  closed: "closed",
  removed: "removed",
};

const GROUP_WORDS: Record<PortalPetitionGroup, string> = {
  open: "Open for signatures",
  awaiting: "With the MCE",
  responded: "Answered",
  closed: "Closed",
  removed: "Removed",
};

/** The server's own status words once they have arrived, and the same words in this build until they do. */
export function groupLabel(group: PortalPetitionGroup, words?: Record<string, string>): string {
  return words?.[GROUP_STATUS[group]] ?? GROUP_WORDS[group];
}

/** A removed petition is in no group, so "removed" counts the removal record rather than a list. */
export function groupCount(group: PortalPetitionGroup, page?: PetitionPage): number | undefined {
  if (!page) return undefined;
  return group === "removed" ? page.removals.total : page.counts[group];
}

/** Which group the API is asked to list while a group is on screen; "removed" lists none, so it borrows "open". */
export function listedGroup(group: PortalPetitionGroup): PetitionGroup {
  return group === "removed" ? "open" : group;
}

const EMPTY: Record<PortalPetitionGroup, string> = {
  open: "No petitions are open for signatures.",
  awaiting: "No petition is waiting for your response.",
  responded: "You haven't answered a petition yet.",
  closed: "No petitions have closed.",
  removed: "No petition has been removed.",
};

export function emptyGroup(group: PortalPetitionGroup): string {
  return EMPTY[group];
}

export const petitionHref = (code: string) => `/portal/mce/petitions/${encodeURIComponent(code)}`;

/**
 * Sharing a petition with a department asks that department to answer it. It settles nothing: the MCE's own
 * response is a separate act, and the same petition can go to more than one department.
 */
export const SHARE_IS_AN_ASK =
  "This asks the department to answer. It isn't a decision on the petition, and it isn't your response: the "
  + "petition's status doesn't move, and it keeps taking signatures. You can ask more than one department.";

/** Said above the field, before a word is written: a note stands under the department, never under the officer. */
export const NOTE_IS_PUBLIC =
  "Your note is published on the petition's public page under your department's name. Your own name is never "
  + "shown with it. Your department writes one note, and it can't be changed or taken back afterwards.";

/** The departments this petition has not gone to yet. The share carries the department's name, as the list does. */
export function notYetAsked(departments: Option[], shared: PetitionDepartmentShare[]): Option[] {
  const asked = new Set(shared.map((share) => share.department));
  return departments.filter((department) => !asked.has(department.name));
}

/** For the MCE: when a department was asked, and whether it has answered. */
export function askedLine(share: PetitionDepartmentShare): string {
  const asked = `Asked on ${formatDate(share.shared_at)}`;
  return share.note_at ? `${asked} · answered on ${formatDate(share.note_at)}` : `${asked} · no answer yet`;
}

/** For the department: what it was asked, and what it has said. */
export function noteLine(shared: SharedPetition): string {
  const asked = `Shared with you on ${formatDate(shared.shared_at)}`;
  return shared.note_at ? `${asked} · you answered on ${formatDate(shared.note_at)}` : asked;
}

/** What the department still owes, and what it has already said. A department writes one note per petition. */
export function splitShared(shared: SharedPetition[]): { waiting: SharedPetition[]; answered: SharedPetition[] } {
  return {
    waiting: shared.filter((item) => item.note === null),
    answered: shared.filter((item) => item.note !== null),
  };
}
