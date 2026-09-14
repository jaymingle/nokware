import { describe, expect, it } from "vitest";

import { chartScale, formatCount, formatDays, monthLabel, percent, periodLabel, shownRuns } from "@/lib/report/dashboard";
import { reportFormData, type ReportDraft } from "@/lib/report/form";
import { addPhotos } from "@/lib/report/photos";
import { normaliseReference } from "@/lib/report/reference";
import { stageOf, statusTag } from "@/lib/report/status";

import type { ReportStatus } from "@/lib/api/types";

const MB = 1024 * 1024;
const LIMITS = { maxPhotos: 3, maxBytes: 10 * MB };
const photo = (name: string, size = MB, type = "image/jpeg") => new File([new Uint8Array(size)], name, { type });

describe("addPhotos", () => {
  it("keeps photos the API takes and says why the others were left out", () => {
    const { photos, problem } = addPhotos([], [photo("a.jpg"), photo("b.heic", MB, "image/heic"), photo("c.png", 11 * MB, "image/png")], LIMITS);
    expect(photos.map((p) => p.name)).toEqual(["a.jpg"]);
    expect(problem).toContain("b.heic isn't a JPEG, PNG or WebP photo.");
    expect(problem).toContain("c.png is 11.0 MB; each photo can be up to 10 MB.");
  });

  it("stops at the limit", () => {
    const { photos, problem } = addPhotos([photo("a.jpg"), photo("b.jpg")], [photo("c.jpg"), photo("d.jpg")], LIMITS);
    expect(photos).toHaveLength(3);
    expect(problem).toBe("You can attach up to 3 photos.");
  });
});

const DRAFT: ReportDraft = {
  description: "  The drain by the school is choked.  ",
  ward: "kinka",
  phone: "024 123 4567",
  whatsapp: " ",
  notify: false,
  callbackConsent: false,
  photos: [],
};

describe("reportFormData", () => {
  it("sends an everyday report's fields, trimmed, and no safety flags", () => {
    const form = reportFormData(DRAFT);
    expect(form.get("description")).toBe("The drain by the school is choked.");
    expect([form.get("ward"), form.get("phone"), form.get("whatsapp"), form.get("notify")]).toEqual(["kinka", "024 123 4567", null, null]);
  });

  it("on the safety form, sends a number only with an opt-in", () => {
    const safety = { ...DRAFT, ward: undefined, safetyTopic: "abuse", subMetro: "ablekuma-south" };
    expect(reportFormData(safety).get("phone")).toBeNull();
    const agreed = reportFormData({ ...safety, callbackConsent: true });
    expect([agreed.get("phone"), agreed.get("callback_consent"), agreed.get("notify"), agreed.get("safety_topic")]).toEqual([
      "024 123 4567", "true", "false", "abuse",
    ]);
  });

  it("attaches every photo under one name", () => {
    expect(reportFormData({ ...DRAFT, photos: [photo("a.jpg"), photo("b.jpg")] }).getAll("photos")).toHaveLength(2);
  });
});

describe("normaliseReference", () => {
  it("reads a reference as a citizen might type it", () => {
    expect(normaliseReference(" k7qm 4txp ")).toBe("K7QM-4TXP");
    expect(normaliseReference("K7QM-4TX0")).toBeNull(); // 0 is never used
    expect(normaliseReference("K7QM")).toBeNull();
    expect(normaliseReference("6F1C2A9E-0B7D-4C3E-9A1B-2C3D4E5F6A7B")).toBe("6f1c2a9e-0b7d-4c3e-9a1b-2c3d4e5f6a7b");
  });
});

const civic = (fields: Partial<ReportStatus>): ReportStatus => ({
  reference: "K7QM-4TXP", case_id: "c1", private: false, submitted_at: "2026-09-01T10:00:00Z", escalated: false,
  escalate_until: null, recipients: [], resolution_notes: [], ...fields,
});

describe("status wording", () => {
  it("shows three stages, and a safety case only its stage", () => {
    expect(stageOf(civic({ status: "assigned" }))).toBe("received");
    expect(stageOf(civic({ status: "escalated" }))).toBe("in_progress");
    expect(stageOf(civic({ private: true, stage: "completed" }))).toBe("completed");
    expect(statusTag(civic({ private: true, stage: "completed" })).label).toBe("Completed");
  });

  it("names an escalation, and a resolution after it", () => {
    expect(statusTag(civic({ status: "escalated", escalated: true }))).toEqual({ tone: "brick", label: "With the MCE's office" });
    expect(statusTag(civic({ status: "resolved", escalated: true })).label).toBe("Resolved after review");
  });
});

describe("dashboard figures", () => {
  it("labels months and the period", () => {
    const months = [{ month: "2025-10", received: 0, resolved: 0 }, { month: "2026-09", received: 1, resolved: 0 }];
    expect(monthLabel("2025-10")).toBe("Oct");
    expect(periodLabel(months)).toBe("October 2025 to September 2026");
  });

  it("formats shares and days", () => {
    expect([percent(1, 3), percent(0, 0)]).toEqual(["33%", "0%"]);
    expect([formatDays(0.3), formatDays(16.6)]).toEqual(["under 1", "17"]);
  });

  it("scales the chart to whole, even steps", () => {
    expect(chartScale([0, 2, 1])).toEqual({ max: 4, ticks: [0, 1, 2, 3, 4] });
    expect(chartScale([])).toEqual({ max: 4, ticks: [0, 1, 2, 3, 4] });
    expect(chartScale([668, 412]).max).toBe(800);
  });
});

describe("counts of fewer than 5", () => {
  it("reads <5, hides shares it would reveal, and breaks the chart's line", () => {
    expect([formatCount(null), formatCount(1204)]).toEqual(["<5", (1204).toLocaleString()]);
    expect([percent(null, 12), percent(3, null), percent(6, 12)]).toEqual([null, null, "50%"]);
    expect(shownRuns([5, 6, null, 7, null, null, 8, 9])).toEqual([[0, 1], [3], [6, 7]]);
    expect(chartScale([null, 2]).max).toBe(4);
  });
});
