import type { AskChart, ChartValue } from "@/lib/api/types";

// The API (ask_charts.py) decides a chart's kind, values and axis; these only work out where things go.

export const RANGE_KEY =
  "Hatched or dashed: “fewer than 5”, somewhere from 1 to 4. Nokware never shows these counts exactly, so they're drawn as a range, not a value.";

const COLOURS = [
  "var(--teal)", "var(--gold)", "var(--brick)", "var(--ink-soft)",
  "color-mix(in srgb, var(--teal) 55%, white)", "color-mix(in srgb, var(--gold) 55%, white)", "color-mix(in srgb, var(--brick) 55%, white)",
];

export function colour(index: number): string {
  return COLOURS[index % COLOURS.length];
}

/** "Fewer than 5" is a range, 1 to 4: never drawn as a value. */
export function isRange(value: ChartValue): boolean {
  return value.low !== value.high;
}

export function hasRange(chart: AskChart): boolean {
  return chart.series.some((series) => series.values.some(isRange));
}

/**
 * Large ticks are shortened because "25,000,000" at every tick of a budget axis
 * runs together. Only the ruler is shortened: amounts stand in full on the bars,
 * in the figures card and in every export.
 */
export function tickLabel(tick: number): string {
  const size = Math.abs(tick);
  if (size >= 1_000_000) return `${trim(tick / 1_000_000)}m`;
  if (size >= 10_000) return `${trim(tick / 1_000)}k`;
  return tick.toLocaleString("en-GB", { minimumFractionDigits: Number.isInteger(tick) ? 0 : 2, maximumFractionDigits: 2 });
}

function trim(value: number): string {
  return value.toLocaleString("en-GB", { maximumFractionDigits: 1 });
}

export function short(value: ChartValue): string {
  return isRange(value) ? "<5" : value.shown;
}

/** One bar, or one stacked segment: where it sits across its category's band (0 to 1), and the values it spans. */
export type BarPiece = { category: number; series: number; offset: number; thickness: number; from: number; to: number; value: ChartValue };

/** bandPixels and maxBar keep a bar from growing into a slab when there are only a few categories. */
export function barPieces(chart: AskChart, bandPixels = 1, maxBar = Infinity): BarPiece[] {
  const stacked = chart.kind === "stacked_bar";
  const count = chart.series.length;
  const band = Math.min(stacked || count === 1 ? 0.6 : 0.8, (maxBar * (stacked ? 1 : count)) / bandPixels);
  const thickness = stacked ? band : band / count;
  return chart.categories.flatMap((_, category) => {
    let base = 0;
    return chart.series.map((series, index) => {
      const value = series.values[category];
      const from = stacked ? base : isRange(value) ? value.low : 0;
      const to = stacked ? base + value.high : value.high;
      base = stacked ? to : base;
      return { category, series: index, offset: (1 - band) / 2 + (stacked ? 0 : thickness * index), thickness, from, to, value };
    });
  });
}

/** Runs of consecutive exact counts: a line breaks at a "fewer than 5" point rather than guess where it would be. */
export function exactRuns(values: ChartValue[]): number[][] {
  const runs: number[][] = [];
  let run: number[] = [];
  values.forEach((value, index) => {
    if (isRange(value)) {
      if (run.length) runs.push(run);
      run = [];
    } else {
      run.push(index);
    }
  });
  return run.length ? [...runs, run] : runs;
}

/** Clockwise from twelve o'clock, in radians. A pie only ever has exact counts. */
export function slices(chart: AskChart): { start: number; end: number; share: number }[] {
  const values = chart.series[0]?.values.map((value) => value.high) ?? [];
  const total = values.reduce((sum, value) => sum + value, 0) || 1;
  let angle = 0;
  return values.map((value) => {
    const start = angle;
    angle += (2 * Math.PI * value) / total;
    return { start, end: angle, share: Math.round((100 * value) / total) };
  });
}

function point(cx: number, cy: number, r: number, angle: number): string {
  return `${(cx + r * Math.sin(angle)).toFixed(2)} ${(cy - r * Math.cos(angle)).toFixed(2)}`;
}

export function arcPath(cx: number, cy: number, r: number, inner: number, start: number, end: number): string {
  const sweep = Math.min(end - start, 2 * Math.PI - 0.0001);
  const large = sweep > Math.PI ? 1 : 0;
  const last = start + sweep;
  const outer = `M ${point(cx, cy, r, start)} A ${r} ${r} 0 ${large} 1 ${point(cx, cy, r, last)}`;
  if (inner <= 0) return `${outer} L ${cx} ${cy} Z`;
  return `${outer} L ${point(cx, cy, inner, last)} A ${inner} ${inner} 0 ${large} 0 ${point(cx, cy, inner, start)} Z`;
}
