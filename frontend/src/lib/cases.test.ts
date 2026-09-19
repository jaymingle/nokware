import { describe, expect, it } from "vitest";

import { arrange, caseAge, caseEventText, caseNoteCopy, caseNoteReader, caseStatusTag, caseTrail, openForMe } from "@/lib/cases";

import type { CaseDetail, CaseEvent, CaseSummary } from "@/lib/api/types";

const NOW = Date.parse("2026-09-13T12:00:00Z");

describe("caseStatusTag", () => {
  it("shows the caller's own part, and escalation above all", () => {
    expect(caseStatusTag({ status: "in_progress", my_status: "resolved" }).label).toBe("Resolved");
    expect(caseStatusTag({ status: "assigned", my_status: null }).label).toBe("New");
    expect(caseStatusTag({ status: "escalated", my_status: "resolved" })).toEqual({ tone: "brick", label: "Escalated to the MCE" });
  });
});

describe("caseAge", () => {
  it("counts hours, then days", () => {
    expect(caseAge("2026-09-13T11:30:00Z", NOW)).toBe("<1h");
    expect(caseAge("2026-09-13T07:00:00Z", NOW)).toBe("5h");
    expect(caseAge("2026-09-10T12:00:00Z", NOW)).toBe("3d");
  });
});

describe("openForMe", () => {
  it("counts cases with something left to do", () => {
    const cases = [{ allowed_actions: ["resolve"] }, { allowed_actions: [] }] as unknown as CaseSummary[];
    expect(openForMe(cases)).toBe(1);
  });
});

describe("caseEventText", () => {
  it("prefers the entry's note, and names bare steps plainly", () => {
    expect(caseEventText({ action: "submitted", note: null })).toBe("Reported by a resident");
    expect(caseEventText({ action: "resolved", note: "Resolved by Works. Drain desilted." })).toBe("Resolved by Works. Drain desilted.");
  });
});

describe("a staff note's reader", () => {
  it("names the resident on an everyday case", () => {
    expect(caseNoteCopy(false).label).toBe("The resident will see this note");
    expect(caseNoteCopy(false).hint).toBe("Say what was done or what happens next. Don't include names, phone numbers or addresses.");
    expect(caseNoteReader(false)).toBe("The resident reads this note");
  });

  it("says a personal-safety note is internal, in the field and in the trail alike", () => {
    expect(caseNoteCopy(true).label).toBe("Internal: not shown to the resident");
    expect(caseNoteCopy(true).hint).toContain("audit trail");
    expect(caseNoteReader(true)).toBe("Internal: not shown to the resident");
  });
});

describe("caseTrail", () => {
  // seen_by_the_resident is the API's answer, not a rule this file keeps: these events carry it as the server would.
  const event = (action: string, staffNote: string | null = null, seen = true) =>
    ({ action, actor_name: "Waste Management", actor_role: "department", note: null, staff_note: staffNote,
       at: "2026-09-12T09:00:00Z", seen_by_the_resident: seen }) as CaseEvent;
  const trail = (isPrivate: boolean, history: CaseEvent[]) => caseTrail({ private: isPrivate, history } as Pick<CaseDetail, "private" | "history">);

  it("keeps the order the case took, and marks the steps the resident reads", () => {
    const steps = trail(false, [event("submitted"), event("notified", null, false), event("resolved", "Drain desilted.")]);
    expect(steps.map((step) => [step.event.action, step.seen])).toEqual([["submitted", true], ["notified", false], ["resolved", true]]);
    expect(steps[2].note).toBe("Drain desilted.");
    expect(steps[2].internal).toBe(false);
  });

  it("marks every note internal on a personal-safety case, where the page shows only how far it has got", () => {
    const steps = trail(true, [event("acknowledged", "Officer visited."), event("reassigned", "Police hold it now.", false)]);
    expect(steps.map((step) => step.seen)).toEqual([true, false]);
    expect(steps.every((step) => step.internal)).toBe(true);
  });
});

describe("the department's own queue", () => {
  const summary = (id: string, my: string | null, status = "assigned", submittedAt = "2026-09-10T09:00:00Z") =>
    ({ case_id: id, my_status: my, status, submitted_at: submittedAt }) as CaseSummary;

  it("shows a case by the part that belongs to this department, not the case's own status", () => {
    const mine = [summary("a", "assigned"), summary("b", "in_progress", "in_progress"), summary("c", "resolved", "in_progress")];
    expect(arrange(mine, "new", "urgent").map((c) => c.case_id)).toEqual(["a"]);
    expect(arrange(mine, "in_progress", "urgent").map((c) => c.case_id)).toEqual(["b"]);
    // Resolved by this department, while another recipient is still working: it is done for them.
    expect(arrange(mine, "resolved", "urgent").map((c) => c.case_id)).toEqual(["c"]);
    expect(arrange(mine, "all", "urgent")).toHaveLength(3);
  });

  it("leaves an escalated case out of new and in progress: it is the MCE's now", () => {
    const escalated = [summary("a", "assigned", "escalated"), summary("b", "in_progress", "escalated")];
    expect(arrange(escalated, "new", "urgent")).toEqual([]);
    expect(arrange(escalated, "in_progress", "urgent")).toEqual([]);
  });

  it("keeps the triage order given by the API until newest first is asked for", () => {
    const queue = [summary("older", "assigned", "assigned", "2026-09-01T09:00:00Z"), summary("newer", "assigned", "assigned", "2026-09-12T09:00:00Z")];
    expect(arrange(queue, "all", "urgent").map((c) => c.case_id)).toEqual(["older", "newer"]);
    expect(arrange(queue, "all", "newest").map((c) => c.case_id)).toEqual(["newer", "older"]);
  });
});
