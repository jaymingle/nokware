// Accra keeps GMT all year (no daylight saving), so times are shown as GMT.
const TIME_ZONE = "Africa/Accra";
const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;

export const URGENT_WITHIN_MS = 12 * HOUR_MS;

type Urgency = "normal" | "urgent" | "passed";

type Deadline = { remainingMs: number; label: string; urgency: Urgency };

export function formatRemaining(remainingMs: number): string {
  if (remainingMs <= 0) return "0m";
  if (remainingMs < MINUTE_MS) return "under a minute";
  const hours = Math.floor(remainingMs / HOUR_MS);
  const minutes = Math.floor((remainingMs % HOUR_MS) / MINUTE_MS);
  return hours > 0 ? `${hours}h ${String(minutes).padStart(2, "0")}m` : `${minutes}m`;
}

export function deadlineFrom(iso: string, now: number): Deadline {
  const remainingMs = Date.parse(iso) - now;
  let urgency: Urgency = "normal";
  if (remainingMs <= 0) urgency = "passed";
  else if (remainingMs <= URGENT_WITHIN_MS) urgency = "urgent";
  return { remainingMs, label: formatRemaining(remainingMs), urgency };
}

const dateTimeFormat = new Intl.DateTimeFormat("en-GB", {
  timeZone: TIME_ZONE,
  weekday: "short",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

const dateFormat = new Intl.DateTimeFormat("en-GB", {
  timeZone: TIME_ZONE,
  day: "numeric",
  month: "short",
  year: "numeric",
});

export function formatDateTime(iso: string): string {
  return `${dateTimeFormat.format(new Date(iso))} GMT`;
}

export function formatDate(iso: string): string {
  return dateFormat.format(new Date(iso));
}

/** The machine-readable instant for a <time> element. Unreadable timestamps are passed through. */
export function machineTime(iso: string): string {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toISOString();
}
