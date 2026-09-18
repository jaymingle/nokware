import { describe, expect, it } from "vitest";

import { arrange, caseAge, caseEventText, caseStatusTag, openForMe } from "@/lib/cases";

import type { CaseSummary } from "@/lib/api/types";

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
