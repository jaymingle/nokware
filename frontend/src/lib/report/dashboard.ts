import type { MonthFigures } from "@/lib/api/types";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const LONG_MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];
const CHART_STEPS = 4;
const NICE = [1, 2, 2.5, 5, 10];

function parts(key: string): [number, number] {
  const [year, month] = key.split("-").map(Number);
  return [year, month - 1];
}

export function monthLabel(key: string): string {
  return MONTHS[parts(key)[1]];
}

export function longMonth(key: string): string {
  const [year, month] = parts(key);
  return `${LONG_MONTHS[month]} ${year}`;
}

export function periodLabel(months: MonthFigures[]): string {
  if (months.length === 0) return "";
  return `${longMonth(months[0].month)} to ${longMonth(months[months.length - 1].month)}`;
}

// A report count of null means 1 to 4, shown as "fewer than 5" (the API's rule, as in Ask).
export type Count = number | null;
export const FEWER_THAN_FIVE = "fewer than 5";
const SUPPRESSED_MAX = 4; // the most a "fewer than 5" count can be
/** So a chart draws "fewer than 5" as a range instead of guessing a point. */
export const SUPPRESSED_RANGE: readonly [number, number] = [1, SUPPRESSED_MAX];

export function formatCount(count: Count): string {
  return count === null ? "<5" : count.toLocaleString();
}

export function percent(count: Count, total: Count): string | null {
  if (count === null || total === null) return null;
  return total > 0 ? `${Math.round((count / total) * 100)}%` : "0%";
}

export function drawnValue(count: Count): number {
  return count ?? SUPPRESSED_MAX;
}

/** So a line breaks at "fewer than 5" instead of guessing. */
export function shownRuns(values: Count[]): number[][] {
  const runs: number[][] = [];
  values.forEach((value, i) => {
    if (value === null) return;
    const last = runs[runs.length - 1];
    if (last && last[last.length - 1] === i - 1) last.push(i);
    else runs.push([i]);
  });
  return runs;
}

export function formatDays(days: number): string {
  if (days < 1) return "under 1";
  return String(Math.round(days));
}

export function chartScale(values: Count[]): { max: number; ticks: number[] } {
  const highest = Math.max(0, ...values.map(drawnValue));
  const rough = highest / CHART_STEPS;
  const magnitude = 10 ** Math.floor(Math.log10(Math.max(rough, 1)));
  const step = Math.max(1, (NICE.find((n) => n * magnitude >= rough) ?? 10) * magnitude);
  const whole = Math.ceil(step);
  const max = whole * CHART_STEPS;
  return { max, ticks: Array.from({ length: CHART_STEPS + 1 }, (_, i) => i * whole) };
}
