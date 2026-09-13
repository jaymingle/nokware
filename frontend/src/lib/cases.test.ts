import { describe, expect, it } from "vitest";

import { caseAge, caseEventText, caseStatusTag, openForMe } from "@/lib/cases";

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
