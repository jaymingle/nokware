import { describe, expect, it } from "vitest";

import { countedAt, isFigureLabel, labelNumber, markFiguresCited } from "@/lib/ask/figures";
import { linkCitations } from "@/lib/ask/sources";

import type { AskFigure } from "@/lib/api/types";

const figure = (label: string): AskFigure => ({
  label, cited: false, description: "Open reports · since Nokware began", value: "fewer than 5", rows: [], counted_at: "2026-09-14T02:31:00+00:00",
});

describe("live figures", () => {
  it("tells figure labels from document labels, and numbers both", () => {
    expect([isFigureLabel("R1"), isFigureLabel("S1")]).toEqual([true, false]);
    expect([labelNumber("R12"), labelNumber("S3")]).toEqual(["12", "3"]);
  });

  it("marks the figures the answer cites", () => {
    expect(markFiguresCited([figure("R1"), figure("R2")], ["S1", "R2"]).map((f) => f.cited)).toEqual([false, true]);
  });

  it("links figure citations like document ones", () => {
    expect(linkCitations("Fewer than 5 are open [R1][S2].")).toBe("Fewer than 5 are open [R1](#cite-R1)[S2](#cite-S2).");
  });

  it("says when a figure was counted, in Accra time", () => {
    expect(countedAt("2026-09-14T02:31:00+00:00")).toBe("Counted 14 Sept, 02:31 GMT");
  });
});
