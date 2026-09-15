import type { DepartmentFigures, PublishingRecord, RecordPeriod, RecordRequirement } from "@/lib/api/types";

// The publishing record says what a gap is, and no more: a document not in the
// Ledger may exist and simply not be online, so a gap is "not found in the
// Documents Centre and not in The Ledger", never "does not exist".

export type RecordState = RecordPeriod["state"];

export const STATE_LABELS: Record<RecordState, string> = {
  held: "In The Ledger",
  related: "Related documents only",
  missing: "Not found",
  not_due: "Not yet expected",
};

const longDate = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

export function dateLabel(isoDate: string): string {
  return longDate.format(new Date(`${isoDate.slice(0, 10)}T00:00:00Z`));
}

/** The one sentence a gap is allowed to say. */
export function gapSentence(checked: string): string {
  return `Not found in ama.gov.gh's Documents Centre (checked ${dateLabel(checked)}) and not in The Ledger.`;
}

export const ASSUMPTION_NOTE =
  "The “Expected…” dates under each document are our own conservative assumptions of when it is due, not statutory deadlines. The statutory dates under the Local Governance Act, 2016 (Act 936) should be confirmed before this record is used for real.";

export function yearsOf(record: PublishingRecord): number[] {
  return Array.from({ length: record.last_year - record.first_year + 1 }, (_, i) => record.first_year + i);
}

/** The periods a requirement shows under one year: one, four quarters, or the plan period covering it. */
export function periodsIn(requirement: RecordRequirement, year: number): RecordPeriod[] {
  if (requirement.cadence === "plan_period") {
    return requirement.periods.filter((p) => p.year <= year && year < p.year + 4);
  }
  return requirement.periods.filter((p) => p.year === year);
}

/** How many columns (years) a plan period spans in the table, from the first year shown. */
export function planSpan(period: RecordPeriod, years: number[]): number {
  return years.filter((year) => period.year <= year && year < period.year + 4).length;
}

/** The request someone can send under the RTI Act, worded for this document and period. */
export function requestWording(documentName: string, period: string, issuedElsewhere: boolean): string {
  const subject = issuedElsewhere ? `the ${documentName} on the Accra Metropolitan Assembly` : `the Accra Metropolitan Assembly's ${documentName}`;
  return `Under the Right to Information Act, 2019 (Act 989), I request a copy of ${subject} for ${period}.`;
}

export function rtiHref(requirement: RecordRequirement, period: RecordPeriod): string {
  const params = new URLSearchParams({ document: requirement.name, period: period.label });
  if (requirement.issued_by) params.set("elsewhere", "1");
  return `/rti?${params}`;
}

/** Whether a department had anything to show in the period: most never receive reports. */
export function isActive(department: DepartmentFigures): boolean {
  const counts = [department.reports.received, department.documents.accepted, department.documents.disputed, department.documents.auto_published];
  return counts.some((value) => value !== 0);
}
