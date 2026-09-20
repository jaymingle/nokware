import { describe, expect, it } from "vitest";

import { STATUS_LABELS, TIMELINE_WORDS } from "@/lib/petitions";
import {
  caseEventTone, caseStatus, disputeStatus, historyTone, ingestionStatus, issueStage, ledgerStatus, petitionEventTone,
  petitionStatus, recordStatus, reportEventTone, reportStatus, submissionTone, unknownStatus, type StatusTone,
} from "@/lib/status";

import type { HistoryAction, IngestionState, PetitionStatus, PetitionTimelineEntry, RecordPeriod, ReportStatus } from "@/lib/api/types";

const TONES: StatusTone[] = ["waiting", "active", "attention", "done", "ended"];

const report = (fields: Partial<ReportStatus>): ReportStatus => ({
  reference: "K7QM-4TXP", case_id: "c1", private: false, submitted_at: "2026-09-01T10:00:00Z", escalated: false,
  escalate_until: null, recipients: [], resolution_notes: [], ...fields,
});

describe("a case's status", () => {
  it("gives every status the department's queue can hold a tone and words", () => {
    const statuses = ["submitted", "assigned", "in_progress", "resolved", "escalated"];
    for (const status of statuses) {
      const meaning = caseStatus({ status, my_status: null });
      expect(TONES).toContain(meaning.tone);
      expect(meaning.label).not.toBe("");
    }
  });

  it("reads the caller's own part, with escalation above all", () => {
    expect(caseStatus({ status: "assigned", my_status: null })).toEqual({ tone: "waiting", label: "New" });
    expect(caseStatus({ status: "in_progress", my_status: "in_progress" })).toEqual({ tone: "active", label: "In progress" });
    expect(caseStatus({ status: "in_progress", my_status: "resolved" })).toEqual({ tone: "done", label: "Resolved" });
    expect(caseStatus({ status: "escalated", my_status: "resolved" })).toEqual({ tone: "attention", label: "Escalated to the MCE" });
  });
});

describe("a state nobody here has met", () => {
  it("says it in words under the neutral tone, rather than a bare or alarming tag", () => {
    expect(caseStatus({ status: "on_hold", my_status: null })).toEqual({ tone: "waiting", label: "On hold" });
    expect(caseStatus({ status: "in_progress", my_status: "gone_quiet" })).toEqual({ tone: "waiting", label: "Gone quiet" });
    expect(unknownStatus("")).toEqual({ tone: "waiting", label: "Not known" });
    expect(unknownStatus(null)).toEqual({ tone: "waiting", label: "Not known" });
  });

  it("falls back to waiting for an unknown step of any trail", () => {
    expect(caseEventTone("archived")).toBe("waiting");
    expect(reportEventTone("archived")).toBe("waiting");
  });
});

describe("a personal-safety case", () => {
  // The page shows how far the case has got and nothing else. The tag may not add to it.
  it("keeps the three words it has today, at every stage", () => {
    expect(reportStatus(report({ private: true, stage: "received" })).label).toBe("Received");
    expect(reportStatus(report({ private: true, stage: "in_progress" })).label).toBe("In progress");
    expect(reportStatus(report({ private: true, stage: "completed" })).label).toBe("Completed");
  });

  it("stays neutral: completed claims no outcome, and an escalation is never named", () => {
    expect(reportStatus(report({ private: true, stage: "completed" })).tone).toBe("ended");
    const escalated = report({ private: true, stage: "in_progress", status: "escalated", escalated: true });
    expect(reportStatus(escalated)).toEqual({ tone: "active", label: "In progress" });
  });

  it("differs from an everyday report, which does say where it went and how it ended", () => {
    expect(reportStatus(report({ status: "resolved" }))).toEqual({ tone: "done", label: "Resolved" });
    expect(reportStatus(report({ status: "escalated", escalated: true }))).toEqual({ tone: "attention", label: "With the MCE's office" });
    expect(reportStatus(report({ status: "resolved", escalated: true })).label).toBe("Resolved after review");
  });
});

describe("a petition", () => {
  it("gives every status its tone, and the words the rest of the site uses", () => {
    for (const status of Object.keys(STATUS_LABELS) as PetitionStatus[]) {
      expect(petitionStatus(status)).toEqual({ tone: expect.any(String), label: STATUS_LABELS[status] });
      expect(TONES).toContain(petitionStatus(status).tone);
    }
  });

  it("separates what is running from what is over", () => {
    expect(petitionStatus("open").tone).toBe("active");
    expect(petitionStatus("awaiting_response").tone).toBe("waiting");
    expect(petitionStatus("responded").tone).toBe("done");
    expect(petitionStatus("closed").tone).toBe("ended");
  });

  it("makes a removal an ending, not an alarm: it can be mended and published again", () => {
    expect(petitionStatus("removed").tone).toBe("ended");
  });

  it("gives every step of its timeline a tone", () => {
    // Read from the words the page shows, which the type makes exhaustive: a new step can't be given one and not
    // the other.
    for (const action of Object.keys(TIMELINE_WORDS) as PetitionTimelineEntry["action"][]) {
      expect(TONES).toContain(petitionEventTone(action));
    }
    expect(petitionEventTone("no_response")).toBe("attention");
  });
});

describe("a document", () => {
  it("gives every ledger status and every review state a tone", () => {
    for (const status of ["held", "published", "disputed", "withdrawn"] as const) {
      expect(TONES).toContain(ledgerStatus(status).tone);
    }
    expect(ledgerStatus("published")).toEqual({ tone: "done", label: "Published" });
    expect(submissionTone("response_needed")).toBe("attention");
    // The clock has run out, but nothing is in the Ledger until the job runs.
    expect(submissionTone("publishing")).toBe("waiting");
    expect(disputeStatus(true).tone).toBe("waiting");
    expect(disputeStatus(false).tone).toBe("waiting");
  });

  it("gives every state of Ask's indexing a tone and words", () => {
    for (const state of ["processing", "searchable", "not_searchable", "failed"] as IngestionState[]) {
      expect(TONES).toContain(ingestionStatus(state).tone);
      expect(ingestionStatus(state).label).not.toBe("");
    }
    expect(ingestionStatus("searchable").tone).toBe("done");
    expect(ingestionStatus("failed").tone).toBe("attention");
  });

  it("gives every entry of a chain of custody a tone", () => {
    const actions: HistoryAction[] = ["uploaded", "submitted", "accepted", "disputed", "dispute_accepted",
      "resubmitted", "escalated", "upheld", "overruled", "auto_published"];
    for (const action of actions) expect(TONES).toContain(historyTone(action));
    expect(historyTone("disputed")).toBe("attention");
    expect(historyTone("upheld")).toBe("ended");
  });
});

describe("the publishing record and the issues beside it", () => {
  it("marks each of the record's four states, with the words the page already uses", () => {
    for (const state of ["held", "related", "missing", "not_due"] as RecordPeriod["state"][]) {
      expect(TONES).toContain(recordStatus(state).tone);
      expect(recordStatus(state).label).not.toBe("");
    }
    expect(recordStatus("held").tone).toBe("done");
    expect(recordStatus("missing").tone).toBe("attention");
    expect(recordStatus("not_due").tone).toBe("ended");
  });

  it("reads an open issue the way a case is read", () => {
    expect(issueStage("received")).toEqual({ tone: "waiting", label: "Received" });
    expect(issueStage("in_progress").tone).toBe("active");
    expect(issueStage("escalated").tone).toBe("attention");
    expect(issueStage("resolved").tone).toBe("done");
  });
});

describe("a case's trail", () => {
  it("gives every step the audit trail can hold a tone", () => {
    const actions = ["submitted", "classified", "assigned", "acknowledged", "resolved", "escalated", "reassigned",
      "reopened", "escalation_confirmed", "reclassified", "notified", "contact_deleted", "location_shared",
      "location_viewed", "location_removed"];
    for (const action of actions) expect(TONES).toContain(caseEventTone(action));
    expect(caseEventTone("acknowledged")).toBe("active");
    expect(caseEventTone("escalated")).toBe("attention");
  });

  it("gives every step the resident reads a tone, under the shorter names that page uses", () => {
    const actions = ["filed", "routed", "started", "reassigned", "resolved", "escalated", "mce_response", "reopened", "closed"];
    for (const action of actions) expect(TONES).toContain(reportEventTone(action));
    expect(reportEventTone("started")).toBe("active");
    expect(reportEventTone("closed")).toBe("ended");
  });
});
