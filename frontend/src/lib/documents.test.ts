import { describe, expect, it } from "vitest";

import { clockRunning, splitHeld } from "@/lib/documents";

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

describe("clockRunning", () => {
  it("is false exactly at the deadline, and true with no clock at all", () => {
    expect(clockRunning(doc("a", "held", inHours(0)), NOW)).toBe(false);
    expect(clockRunning(doc("b", "disputed", null), NOW)).toBe(true);
  });
});
