import { describe, expect, it } from "vitest";

import { historyActor, historyLabel } from "@/lib/history";

import type { HistoryEntry } from "@/lib/api/types";

function entry(actorName: string, actorRole: string): HistoryEntry {
  return {
    action: "disputed",
    actor_name: actorName,
    actor_role: actorRole,
    from_status: "held",
    to_status: "disputed",
    note: null,
    at: "2026-03-10T12:00:00Z",
  };
}

describe("historyActor", () => {
  it("names the person and their role", () => {
    expect(historyActor(entry("Ama Mensah", "contributor"))).toBe("Ama Mensah · Contributor");
    expect(historyActor(entry("Kwame Boateng", "mce"))).toBe("Kwame Boateng · MCE");
  });

  it("has no person for automatic steps, and falls back to the name for unknown roles", () => {
    expect(historyActor(entry("Automatic publication", "system"))).toBeNull();
    expect(historyActor(entry("Legacy", "admin"))).toBe("Legacy");
  });
});

describe("historyLabel", () => {
  it("says what happened, including the automatic publication", () => {
    expect(historyLabel("escalated")).toBe("Escalated to the MCE");
    expect(historyLabel("auto_published")).toBe("Published automatically: the clock ran out");
  });
});
