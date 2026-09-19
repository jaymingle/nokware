import { STATE_LABELS } from "@/lib/accountability";
import { STATUS_LABELS } from "@/lib/petitions";
import { stageLabels, stageOf } from "@/lib/report/status";

import type {
  CaseSummary, HistoryAction, IngestionState, Issue, LedgerStatus, LinkedIssue, PetitionStatus, PetitionTimelineEntry,
  RecordPeriod, ReportStatus,
} from "@/lib/api/types";

/**
 * One status language for the whole of Nokware, portal and public alike: every state the API can send, in one
 * place, mapped onto five tones. A colour therefore means the same thing on a resident's status page as it does
 * in a department's queue, and no component decides for itself what teal means.
 *
 * waiting   — nobody has acted yet: received, routed, with the MCE, awaiting a decision
 * active    — somebody is working on it: acknowledged, in progress, reopened
 * attention — it needs someone now: escalated, disputed, overdue, not found
 * done      — it finished, and the finish is the good one: resolved, responded, published
 * ended     — it finished without one: closed, refused, withdrawn, removed
 *
 * The tones become colours and shapes in exactly one other place, `@/components/status-tag`.
 */
export type StatusTone = "waiting" | "active" | "attention" | "done" | "ended";

/** A state as the reader meets it: the words, and the tone that colours and shapes them. */
export type StatusMeaning = { tone: StatusTone; label: string };

/**
 * A state this build has never met. Case statuses arrive as plain strings, so a new one can reach the browser
 * before this file does. It takes the neutral waiting tone and says the state in words, rather than colouring it
 * as good or bad news, or rendering a tag with nothing in it.
 */
export function unknownStatus(raw: string | null | undefined): StatusMeaning {
  const words = (raw ?? "").replace(/[_-]+/g, " ").trim();
  return { tone: "waiting", label: words ? words[0].toUpperCase() + words.slice(1) : "Not known" };
}

const CASE: Record<string, StatusMeaning> = {
  submitted: { tone: "waiting", label: "Awaiting routing" },
  assigned: { tone: "waiting", label: "New" },
  in_progress: { tone: "active", label: "In progress" },
  resolved: { tone: "done", label: "Resolved" },
  escalated: { tone: "attention", label: "Escalated to the MCE" },
};

/** A case nobody has been given yet. */
export const NEEDS_ROUTING: StatusMeaning = { tone: "waiting", label: "Needs routing" };

/** The tag for a case, from the caller's side: their own part, if they have one. Escalation stands above all. */
export function caseStatus(summary: Pick<CaseSummary, "status" | "my_status">): StatusMeaning {
  if (summary.status === "escalated") return CASE.escalated;
  const own = summary.my_status ?? summary.status;
  return CASE[own] ?? unknownStatus(own);
}

const REPORT_STAGE: Record<string, StatusTone> = { received: "waiting", in_progress: "active", completed: "done" };

/**
 * The tag on a resident's own status page.
 *
 * A personal-safety case keeps the three words and the three tones it has today: received, in progress,
 * completed. "Completed" stays muted rather than taking the success tone, because that page says how far the
 * case got and never what was done — the tag may not claim an outcome the page withholds. Nothing else about
 * such a case reaches the tag: no category, no department, no stage the page doesn't already show.
 */
export function reportStatus(status: ReportStatus): StatusMeaning {
  const stage = stageOf(status);
  const label = stageLabels(status.private)[stage];
  if (status.private) return { tone: stage === "completed" ? "ended" : REPORT_STAGE[stage], label };
  if (status.status === "escalated") return { tone: "attention", label: "With the MCE's office" };
  const reviewed = stage === "completed" && status.escalated;
  return { tone: REPORT_STAGE[stage], label: reviewed ? `${label} after review` : label };
}

const PETITION: Record<PetitionStatus, StatusTone> = {
  awaiting_response: "waiting",
  open: "active",
  responded: "done",
  // Removed is an ending, not an alarm: a petition comes down on a named ground, and can be mended and published
  // again. The brick tone is kept for what needs someone now.
  removed: "ended",
  closed: "ended",
};

export function petitionStatus(status: PetitionStatus): StatusMeaning {
  const tone = PETITION[status];
  return tone ? { tone, label: STATUS_LABELS[status] } : unknownStatus(status);
}

/** The five tabs the public petitions list is filed under, in the same language as the petitions themselves. */
export const PETITION_GROUPS: Record<string, StatusTone> = {
  open: "active", awaiting: "waiting", responded: "done", removed: "ended", closed: "ended",
};

const LEDGER: Record<LedgerStatus, StatusMeaning> = {
  held: { tone: "waiting", label: "With the department" },
  disputed: { tone: "attention", label: "Disputed" },
  published: { tone: "done", label: "Published" },
  withdrawn: { tone: "ended", label: "Withdrawn" },
};

export function ledgerStatus(status: LedgerStatus): StatusMeaning {
  return LEDGER[status] ?? unknownStatus(status);
}

/**
 * A contributor's document as the submissions table reads it: the stored status, and what the review clock has
 * since done to it. "Publishing now" is still waiting — the clock has run out, but nothing is in the Ledger
 * until the job runs.
 */
export type SubmissionState = "held" | "publishing" | "with_mce" | "response_needed" | "published" | "withdrawn";

const SUBMISSION: Record<SubmissionState, StatusTone> = {
  held: "waiting",
  publishing: "waiting",
  with_mce: "waiting",
  response_needed: "attention",
  published: "done",
  withdrawn: "ended",
};

export function submissionTone(state: SubmissionState): StatusTone {
  return SUBMISSION[state] ?? "waiting";
}

/** A department's own open dispute: who it is waiting on. */
export function disputeStatus(escalatedToMce: boolean): StatusMeaning {
  return escalatedToMce
    ? { tone: "waiting", label: "With the MCE" }
    : { tone: "waiting", label: "Waiting for the contributor" };
}

const INGESTION: Record<IngestionState, StatusMeaning> = {
  searchable: { tone: "done", label: "Answerable in Ask" },
  processing: { tone: "active", label: "Processing" },
  // Settled, not a fault being worked on: the scan holds no text, and nothing more will happen to it.
  not_searchable: { tone: "ended", label: "Scanned, not searchable" },
  failed: { tone: "attention", label: "Indexing failed, retrying" },
};

export function ingestionStatus(state: IngestionState): StatusMeaning {
  return INGESTION[state] ?? unknownStatus(state);
}

/**
 * The publishing record's four marks. "Not yet expected" is the one state in Nokware that isn't a state at all —
 * nothing is pending from anyone — so it takes the muted tone and stays out of the way of the gaps the page is
 * there to show.
 */
const RECORD: Record<RecordPeriod["state"], StatusTone> = {
  held: "done", related: "waiting", missing: "attention", not_due: "ended",
};

export function recordStatus(state: RecordPeriod["state"]): StatusMeaning {
  const tone = RECORD[state];
  return tone ? { tone, label: STATE_LABELS[state] } : unknownStatus(state);
}

const ISSUE: Record<string, StatusMeaning> = {
  received: { tone: "waiting", label: "Received" },
  in_progress: { tone: "active", label: "In progress" },
  escalated: { tone: "attention", label: "With the MCE's office" },
  resolved: { tone: "done", label: "Resolved" },
};

/** An open issue on the dashboard, and the same issue cited by a petition. */
export function issueStage(stage: Issue["stage"] | LinkedIssue["stage"]): StatusMeaning {
  return ISSUE[stage] ?? unknownStatus(stage);
}

// Histories and timelines. A step is marked with the tone of what it did, so a trail reads the same way as the
// tag above it. The words beside each mark are the server's or the catalogue's; only the tone is decided here.

const CASE_EVENT: Record<string, StatusTone> = {
  submitted: "waiting", classified: "waiting", assigned: "waiting", reassigned: "waiting", reclassified: "waiting",
  notified: "waiting", acknowledged: "active", reopened: "active", location_shared: "active",
  location_viewed: "active", escalated: "attention", resolved: "done", escalation_confirmed: "done",
  contact_deleted: "ended", location_removed: "ended",
};

/** The audit trail staff read, keyed by the case history's own actions. */
export function caseEventTone(action: string): StatusTone {
  return CASE_EVENT[action] ?? "waiting";
}

const REPORT_EVENT: Record<string, StatusTone> = {
  filed: "waiting", routed: "waiting", reassigned: "waiting", started: "active", reopened: "active",
  escalated: "attention", resolved: "done", mce_response: "done", closed: "ended",
};

/** The same steps as the resident reads them, where the trail uses shorter names for them. */
export function reportEventTone(action: string): StatusTone {
  return REPORT_EVENT[action] ?? "waiting";
}

const HISTORY: Record<HistoryAction, StatusTone> = {
  uploaded: "done", accepted: "done", overruled: "done", auto_published: "done",
  submitted: "waiting", resubmitted: "waiting",
  disputed: "attention", escalated: "attention",
  dispute_accepted: "ended", upheld: "ended",
};

/** A document's chain of custody. */
export function historyTone(action: HistoryAction): StatusTone {
  return HISTORY[action] ?? "waiting";
}

const PETITION_EVENT: Record<PetitionTimelineEntry["action"], StatusTone> = {
  edited: "active", threshold_reached: "active", shared: "active", creator_replied: "active",
  image_removed: "attention",
  moved_to_new_process: "waiting",
  published: "done", republished: "done", responded: "done", department_note: "done",
  no_response: "attention", removed: "ended", withdrawn: "ended", closed: "ended",
};

export function petitionEventTone(action: PetitionTimelineEntry["action"]): StatusTone {
  return PETITION_EVENT[action] ?? "waiting";
}
