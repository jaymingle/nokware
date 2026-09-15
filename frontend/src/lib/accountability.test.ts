import { describe, expect, it } from "vitest";

import { gapSentence, isActive, periodsIn, planSpan, requestWording, rtiHref, yearFromLedger, yearsOf } from "@/lib/accountability";

import type { DepartmentFigures, PublishingRecord, RecordPeriod, RecordRequirement } from "@/lib/api/types";

const period = (label: string, year: number, quarter: number | null = null): RecordPeriod => ({
  label, year, quarter, state: "missing", expected_from: null, documents: [], related: [], nearby: [], nearby_total: 0,
});
const requirement = (cadence: RecordRequirement["cadence"], periods: RecordPeriod[], issuedBy: string | null = null): RecordRequirement => ({
  id: "r", name: "Fee-Fixing Resolution", cadence, issued_by: issuedBy, expected_note: null, nearby_scope: "Finance", periods, undated: [], held: [],
});

describe("the publishing record", () => {
  it("says a gap is not found where we looked, never that the document doesn't exist", () => {
    expect(gapSentence("2026-09-12")).toBe("Not found in ama.gov.gh's Documents Centre (checked 12 September 2026) and not in The Ledger.");
  });

  it("lays quarters and plan periods out under the years they cover", () => {
    const record = { first_year: 2021, last_year: 2026 } as PublishingRecord;
    expect(yearsOf(record)).toEqual([2021, 2022, 2023, 2024, 2025, 2026]);
    const audit = requirement("quarterly", [period("Q1 2024", 2024, 1), period("Q2 2024", 2024, 2), period("Q1 2025", 2025, 1)]);
    expect(periodsIn(audit, 2024).map((p) => p.label)).toEqual(["Q1 2024", "Q2 2024"]);
    const plan = requirement("plan_period", [period("2018–2021", 2018), period("2022–2025", 2022), period("2026–2029", 2026)]);
    expect(periodsIn(plan, 2023).map((p) => p.label)).toEqual(["2022–2025"]);
    expect([planSpan(plan.periods[0], yearsOf(record)), planSpan(plan.periods[1], yearsOf(record)), planSpan(plan.periods[2], yearsOf(record))]).toEqual([1, 4, 1]);
  });

  it("words the RTI request for the document, and for one issued by someone else", () => {
    expect(requestWording("Fee-Fixing Resolution", "2024", false)).toBe(
      "Under the Right to Information Act, 2019 (Act 989), I request a copy of the Accra Metropolitan Assembly's Fee-Fixing Resolution for 2024.");
    expect(requestWording("Auditor-General's Report", "2023", true)).toContain("the Auditor-General's Report on the Accra Metropolitan Assembly for 2023");
    expect(rtiHref(requirement("annual", []), period("2024", 2024))).toBe("/rti?document=Fee-Fixing+Resolution&period=2024");
    expect(rtiHref(requirement("annual", [], "the Auditor-General"), period("2023", 2023))).toContain("&elsewhere=1");
  });
});

describe("where a year came from", () => {
  const held = (...sources: ("title" | "ledger")[]): RecordPeriod => ({
    ...period("2025", 2025), state: "held",
    documents: sources.map((source, i) => ({ id: `d${i}`, title: "Plan", year: 2025, year_source: source, department_name: null, note: null })),
  });

  it("marks a held year only when it rests on the Ledger's record alone", () => {
    expect([yearFromLedger(held("ledger")), yearFromLedger(held("ledger", "title")), yearFromLedger(held("title"))]).toEqual([true, false, false]);
    expect(yearFromLedger(period("2025", 2025))).toBe(false);
  });
});

describe("departmental responsiveness", () => {
  it("lists a department only when it had something counted", () => {
    const quiet = { reports: { received: 0 }, documents: { accepted: 0, disputed: 0, auto_published: 0 } } as DepartmentFigures;
    const few = { reports: { received: null }, documents: { accepted: 0, disputed: 0, auto_published: 0 } } as DepartmentFigures;
    expect([isActive(quiet), isActive(few)]).toEqual([false, true]);
  });
});
