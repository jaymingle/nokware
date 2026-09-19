import { describe, expect, it } from "vitest";

import { deadlineFrom, formatDate, formatDateTime, formatRemaining, machineTime, URGENT_WITHIN_MS } from "@/lib/time";

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const NOW = Date.parse("2026-03-10T12:00:00Z");

describe("formatRemaining", () => {
  it("shows hours and zero-padded minutes", () => {
    expect(formatRemaining(47 * HOUR + 12 * MINUTE)).toBe("47h 12m");
    expect(formatRemaining(71 * HOUR + 5 * MINUTE + 30_000)).toBe("71h 05m");
  });

  it("drops hours under an hour, and seconds entirely", () => {
    expect(formatRemaining(42 * MINUTE + 59_000)).toBe("42m");
    expect(formatRemaining(30_000)).toBe("under a minute");
  });

  it("never counts below zero", () => {
    expect(formatRemaining(0)).toBe("0m");
    expect(formatRemaining(-5 * MINUTE)).toBe("0m");
  });
});

describe("deadlineFrom", () => {
  const at = (ms: number) => new Date(NOW + ms).toISOString();

  it("is normal with more than 12 hours left", () => {
    expect(deadlineFrom(at(URGENT_WITHIN_MS + MINUTE), NOW)).toMatchObject({ urgency: "normal", label: "12h 01m" });
  });

  it("is urgent within the last 12 hours", () => {
    expect(deadlineFrom(at(URGENT_WITHIN_MS), NOW).urgency).toBe("urgent");
    expect(deadlineFrom(at(MINUTE), NOW).urgency).toBe("urgent");
  });

  it("has passed at and after the deadline", () => {
    expect(deadlineFrom(at(0), NOW).urgency).toBe("passed");
    expect(deadlineFrom(at(-HOUR), NOW)).toMatchObject({ urgency: "passed", label: "0m" });
  });

  it("reads Appwrite's offset timestamps", () => {
    expect(deadlineFrom("2026-03-13T12:00:00.000+00:00", NOW).label).toBe("72h 00m");
  });
});

describe("Accra dates", () => {
  it("formats in GMT whatever the viewer's time zone", () => {
    expect(formatDateTime("2026-03-15T14:05:00.000+00:00")).toBe("Sun 15 Mar, 14:05 GMT");
    expect(formatDate("2026-03-15T23:30:00.000+00:00")).toBe("15 Mar 2026");
  });
});

describe("machineTime", () => {
  it("normalises an offset timestamp to a UTC instant", () => {
    expect(machineTime("2026-03-15T14:05:00.000+00:00")).toBe("2026-03-15T14:05:00.000Z");
  });

  it("passes through what it cannot read", () => {
    expect(machineTime("soon")).toBe("soon");
  });
});
