import { afterEach, describe, expect, it, vi } from "vitest";

import { EXPORT_FORMATS, EXPORT_OFFLINE, ExportError, downloadAnswer, filenameFrom, spreadsheetReady } from "@/lib/ask/export";

import type { ExportView } from "@/lib/api/types";

vi.mock("@/lib/env", () => ({ env: { apiUrl: "https://api.nokware.test" } }));

const view = { question: "Q?", token: "t" } as unknown as ExportView;

afterEach(() => vi.unstubAllGlobals());

describe("downloading an answer", () => {
  it("keeps the API's file name, or falls back to a plain one", () => {
    expect(filenameFrom('attachment; filename="nokware-answer-2026-09-14-q.pdf"', "pdf")).toBe("nokware-answer-2026-09-14-q.pdf");
    expect(filenameFrom(null, "csv")).toBe("nokware-answer.csv");
  });

  it("says plainly why a download didn't work", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 403 })));
    await expect(downloadAnswer(view, "pdf")).rejects.toThrow("can't be downloaded");
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 429 })));
    await expect(downloadAnswer(view, "pdf")).rejects.toThrow("a lot of downloads");
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("offline"); }));
    await expect(downloadAnswer(view, "pdf")).rejects.toEqual(new ExportError(EXPORT_OFFLINE));
  });

  it("sends the signed view back with the format asked for", async () => {
    const fetchMock = vi.fn(async () => new Response("{}", { status: 500 }));
    vi.stubGlobal("fetch", fetchMock);
    await downloadAnswer(view, "docx").catch(() => undefined);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("https://api.nokware.test/api/ask/export");
    expect(JSON.parse(String(init.body))).toEqual({ view, format: "docx" });
  });
});

describe("Excel", () => {
  it("is offered for report counts and budget figures, not for numbers quoted from documents", () => {
    const view = (figures: unknown[]) => ({ figures } as unknown as ExportView);
    expect(spreadsheetReady(view([{ label: "R1", source: "reports" }]))).toBe(true);
    expect(spreadsheetReady(view([{ label: "B1", source: "documents" }]))).toBe(true);
    expect(spreadsheetReady(view([]))).toBe(false);  // only [S#] citations: nothing a sheet can hold
  });

  it("is one of the formats offered", () => {
    expect(EXPORT_FORMATS.map((format) => format.format)).toContain("xlsx");
  });
});
