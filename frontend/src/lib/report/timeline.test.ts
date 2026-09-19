import { describe, expect, it } from "vitest";

import { timelineSteps } from "@/lib/report/timeline";

import type { ReportTimelineEvent } from "@/lib/api/types";

function event(over: Partial<ReportTimelineEvent> = {}): ReportTimelineEvent {
  return { action: "filed", at: "2026-03-15T14:05:00.000+00:00", description: "You filed this report.", note: null, ...over };
}

describe("timelineSteps", () => {
  it("keeps the server's order and its sentence as written", () => {
    const steps = timelineSteps([
      event({ action: "filed", description: "You filed this report." }),
      event({ action: "routed", at: "2026-03-16T09:30:00.000+00:00", description: "Sent to Waste Management." }),
    ]);
    expect(steps.map((step) => step.description)).toEqual(["You filed this report.", "Sent to Waste Management."]);
  });

  it("dates and times each step in Accra, and carries the instant for a <time> element", () => {
    const [step] = timelineSteps([event()]);
    expect(step.when).toBe("Sun 15 Mar, 14:05 GMT");
    expect(step.at).toBe("2026-03-15T14:05:00.000Z");
  });

  it("gives every step its own key, even when two share an action and a moment", () => {
    const steps = timelineSteps([event({ action: "routed" }), event({ action: "routed" })]);
    expect(new Set(steps.map((step) => step.key)).size).toBe(2);
  });

  it("has no note where the step has none, and none where the note is only spaces", () => {
    const steps = timelineSteps([event(), event({ note: "   " }), event({ note: " The drain was cleared. " })]);
    expect(steps.map((step) => step.note)).toEqual([null, null, "The drain was cleared."]);
  });

  it("is empty when the report carries no timeline at all", () => {
    expect(timelineSteps(undefined)).toEqual([]);
    expect(timelineSteps([])).toEqual([]);
  });

  it("drops a step with nothing to say", () => {
    expect(timelineSteps([event({ description: "  " }), event()])).toHaveLength(1);
  });
});
