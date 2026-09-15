import { describe, expect, it } from "vitest";

import { arcPath, barPieces, exactRuns, hasRange, short, slices } from "@/lib/ask/chart";

import type { AskChart, ChartValue } from "@/lib/api/types";

const exact = (n: number): ChartValue => ({ shown: String(n), low: n, high: n });
const small: ChartValue = { shown: "fewer than 5", low: 1, high: 4 };
const chart = (kind: AskChart["kind"], series: ChartValue[][]): AskChart => ({
  kind, horizontal: false, title: "Reports", categories: ["Okaikoi South", "Ablekuma South"], over_time: false,
  series: series.map((values, i) => ({ name: `S${i}`, values })), figures: ["R1"], counted_at: "2026-09-14T22:40:00+00:00",
  axis_max: 20, ticks: [0, 5, 10, 15, 20], note: null,
});

describe("Ask charts", () => {
  it("draws “fewer than 5” as the range 1 to 4, never as a value", () => {
    const pieces = barPieces(chart("bar", [[exact(14), small]]));
    expect(pieces.map((p) => [p.from, p.to])).toEqual([[0, 14], [1, 4]]);
    expect([short(small), short(exact(14))]).toEqual(["<5", "14"]);
    expect(hasRange(chart("bar", [[exact(14), small]]))).toBe(true);
  });

  it("sets several counts side by side, and stacks them only when asked", () => {
    const side = barPieces(chart("bar", [[exact(14), exact(9)], [exact(6), exact(7)]]));
    expect(side.filter((p) => p.category === 0).map((p) => [p.offset, p.thickness].map((n) => Math.round(n * 100) / 100))).toEqual([[0.1, 0.4], [0.5, 0.4]]);
    const stacked = barPieces(chart("stacked_bar", [[exact(14), exact(9)], [exact(6), exact(7)]]));
    expect(stacked.filter((p) => p.category === 0).map((p) => [p.from, p.to])).toEqual([[0, 14], [14, 20]]);
  });

  it("breaks a line at a range instead of guessing through it", () => {
    expect(exactRuns([exact(6), exact(9), small, exact(11), small])).toEqual([[0, 1], [3]]);
  });

  it("gives each slice its share and a path that closes", () => {
    const parts = slices(chart("pie", [[exact(15), exact(5)]]));
    expect(parts.map((p) => p.share)).toEqual([75, 25]);
    expect(parts[1].end).toBeCloseTo(2 * Math.PI);
    expect(arcPath(100, 100, 98, 0, parts[0].start, parts[0].end)).toMatch(/^M .* A 98 98 0 1 1 .* L 100 100 Z$/);
    expect(arcPath(100, 100, 98, 27, 0, Math.PI / 2)).toContain("A 27 27 0 0 0");
  });
});
