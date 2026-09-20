import { describe, expect, it } from "vitest";

import { askedLine, notYetAsked, noteLine, splitShared } from "@/lib/portal/petitions";

import type { PetitionCard, PetitionDepartmentShare, SharedPetition } from "@/lib/api/types";

const CARD: PetitionCard = {
  code: "482913", title: "[TEST] Desilt the drain", topic: "Sanitation", departments: ["Waste Management"],
  scope: "area", area: "Kaneshie", sub_metro: "Okaikoi South", status: "open", status_label: "Open for signatures",
  published_at: "2026-09-12T09:00:00Z", closes_at: "2026-12-11T09:00:00Z", closed_at: null, threshold: 150,
  signatures: 12, started_by: null, threshold_reached_at: null, response_due: null, responded_at: null,
  response_label: null, unanswered_at: null, version: 1, versioned_at: null, removals: 0,
};

const SHARED_AT = "2026-09-15T09:00:00Z";
const noteAt = (note: string | null) => (note ? "2026-09-16T09:00:00Z" : null);

function share(department: string, note: string | null): PetitionDepartmentShare {
  return { department, shared_at: SHARED_AT, note, note_at: noteAt(note) };
}

function shared(code: string, note: string | null): SharedPetition {
  return { petition: { ...CARD, code }, shared_at: SHARED_AT, note, note_at: noteAt(note) };
}

describe("the departments a petition has gone to", () => {
  it("leaves out the ones already asked, so the same department isn't asked twice", () => {
    const departments = [{ id: "dept-works", name: "Works Department" }, { id: "dept-legal", name: "Legal Department" }];
    expect(notYetAsked(departments, [share("Works Department", null)])).toEqual([{ id: "dept-legal", name: "Legal Department" }]);
    expect(notYetAsked(departments, [])).toEqual(departments);
  });

  it("says when a department was asked, and whether it has answered", () => {
    expect(askedLine(share("Works Department", null))).toBe("Asked on 15 Sept 2026 · no answer yet");
    expect(askedLine(share("Works Department", "The drain is on the desilting list."))).toBe(
      "Asked on 15 Sept 2026 · answered on 16 Sept 2026");
  });
});

describe("what a department has been asked to answer", () => {
  it("separates what it still owes from what it has already said", () => {
    const queue = [shared("482913", null), shared("504162", "Scheduled for October."), shared("600001", null)];
    const { waiting, answered } = splitShared(queue);
    expect(waiting.map((item) => item.petition.code)).toEqual(["482913", "600001"]);
    expect(answered.map((item) => item.petition.code)).toEqual(["504162"]);
  });

  it("tells the department when the petition reached it, and when it answered", () => {
    expect(noteLine(shared("482913", null))).toBe("Shared with you on 15 Sept 2026");
    expect(noteLine(shared("482913", "Scheduled for October."))).toBe("Shared with you on 15 Sept 2026 · you answered on 16 Sept 2026");
  });
});
