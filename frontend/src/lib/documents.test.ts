import { describe, expect, it } from "vitest";

import { anyPublishingNow, awaitingResponse, clockRunning, describeSubmission, splitByClock, splitHeld } from "@/lib/documents";

import type { DocumentOut } from "@/lib/api/types";

const NOW = Date.parse("2026-03-10T12:00:00Z");
const inHours = (hours: number) => new Date(NOW + hours * 3_600_000).toISOString();

function doc(id: string, status: DocumentOut["status"], heldUntil: string | null): DocumentOut {
  return { id, status, held_until: heldUntil } as DocumentOut;
}

describe("splitHeld", () => {
  it("separates open review windows from ones that have closed, ignoring other statuses", () => {
    const docs = [
      doc("closed", "held", inHours(-0.1)),
      doc("urgent", "held", inHours(5)),
      doc("fresh", "held", inHours(71)),
      doc("disputed", "disputed", null),
    ];
    const { open, closed } = splitHeld(docs, NOW);
    expect(open.map((d) => d.id)).toEqual(["urgent", "fresh"]);
    expect(closed.map((d) => d.id)).toEqual(["closed"]);
  });
});

describe("splitByClock", () => {
  it("splits any documents by their clock, keeping ones with no clock open", () => {
    const docs = [doc("ruled-late", "disputed", inHours(-1)), doc("escalated", "disputed", inHours(30)), doc("no-clock", "disputed", null)];
    const { open, closed } = splitByClock(docs, NOW);
    expect(open.map((d) => d.id)).toEqual(["escalated", "no-clock"]);
    expect(closed.map((d) => d.id)).toEqual(["ruled-late"]);
  });
});

describe("clockRunning", () => {
  it("is false exactly at the deadline, and true with no clock at all", () => {
    expect(clockRunning(doc("a", "held", inHours(0)), NOW)).toBe(false);
    expect(clockRunning(doc("b", "disputed", null), NOW)).toBe(true);
  });
});

describe("describeSubmission", () => {
  const base = { department_name: "Finance", escalated_to_mce: false, resubmission_count: 0 };
  const submission = (fields: Partial<DocumentOut>) => ({ ...base, ...fields }) as DocumentOut;

  it("shows the department's clock while it is held", () => {
    const view = describeSubmission(submission({ status: "held", held_until: inHours(40) }), NOW);
    expect(view).toMatchObject({ label: "With Finance", clock: { unless: "Finance disputes it" } });
  });

  it("asks for a response to an open dispute, with no clock", () => {
    const view = describeSubmission(submission({ status: "disputed", held_until: null }), NOW);
    expect(view).toEqual({ tone: "attention", label: "Your response needed", detail: "Disputed by Finance." });
  });

  it("shows the MCE's clock once escalated, and publishing once it runs out", () => {
    const escalated = submission({ status: "disputed", escalated_to_mce: true, held_until: inHours(10) });
    expect(describeSubmission(escalated, NOW)).toMatchObject({ label: "With the MCE", clock: { unless: "the MCE upholds the dispute" } });
    expect(describeSubmission({ ...escalated, held_until: inHours(-1) }, NOW).label).toBe("Publishing now");
  });

  it("says who withdrew it", () => {
    expect(describeSubmission(submission({ status: "withdrawn" }), NOW).detail).toBe("You accepted the dispute.");
    expect(describeSubmission(submission({ status: "withdrawn", escalated_to_mce: true }), NOW).detail).toBe(
      "The MCE upheld the dispute.",
    );
  });
});

describe("awaitingResponse", () => {
  it("keeps only disputes not yet escalated", () => {
    const docs = [doc("a", "disputed", null), { ...doc("b", "disputed", inHours(5)), escalated_to_mce: true }, doc("c", "held", inHours(5))];
    expect(awaitingResponse(docs as DocumentOut[]).map((d) => d.id)).toEqual(["a"]);
  });
});

describe("anyPublishingNow", () => {
  it("is true only while a held or escalated document's clock has run out", () => {
    expect(anyPublishingNow([doc("a", "held", inHours(-0.01))], NOW)).toBe(true);
    expect(anyPublishingNow([{ ...doc("b", "disputed", inHours(-1)), escalated_to_mce: true }], NOW)).toBe(true);
    expect(anyPublishingNow([doc("c", "held", inHours(3)), doc("d", "published", null)], NOW)).toBe(false);
    expect(anyPublishingNow(undefined, NOW)).toBe(false);
  });
});
