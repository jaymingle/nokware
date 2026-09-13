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

/** "2026-09" as "Sep". */
export function monthLabel(key: string): string {
  return MONTHS[parts(key)[1]];
}

function longMonth(key: string): string {
  const [year, month] = parts(key);
  return `${LONG_MONTHS[month]} ${year}`;
}

/** "October 2025 to September 2026". */
export function periodLabel(months: MonthFigures[]): string {
  if (months.length === 0) return "";
  return `${longMonth(months[0].month)} to ${longMonth(months[months.length - 1].month)}`;
}

/** Share of a total as "72%"; "0%" of nothing. */
export function percent(count: number, total: number): string {
  return total > 0 ? `${Math.round((count / total) * 100)}%` : "0%";
}

/** Median days to resolve, as shown: under a day reads "under 1". */
export function formatDays(days: number): string {
  if (days < 1) return "under 1";
  return String(Math.round(days));
}

/** The chart's top value and gridlines: whole numbers in four even steps. */
export function chartScale(values: number[]): { max: number; ticks: number[] } {
  const highest = Math.max(0, ...values);
  const rough = highest / CHART_STEPS;
  const magnitude = 10 ** Math.floor(Math.log10(Math.max(rough, 1)));
  const step = Math.max(1, (NICE.find((n) => n * magnitude >= rough) ?? 10) * magnitude);
  const whole = Math.ceil(step);
  const max = whole * CHART_STEPS;
  return { max, ticks: Array.from({ length: CHART_STEPS + 1 }, (_, i) => i * whole) };
}
