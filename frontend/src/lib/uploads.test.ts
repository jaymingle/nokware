import { describe, expect, it } from "vitest";

import { formatBytes, MAX_PDF_BYTES, pdfProblem } from "@/lib/uploads";

const file = (name: string, type: string, size: number) => ({ name, type, size });

describe("pdfProblem", () => {
  it("accepts PDFs by type or by extension", () => {
    expect(pdfProblem(file("budget.pdf", "application/pdf", 1000))).toBeNull();
    expect(pdfProblem(file("BUDGET.PDF", "", 1000))).toBeNull();
  });

  it("refuses other files, empty files and files over 50 MB", () => {
    expect(pdfProblem(file("notes.docx", "application/msword", 1000))).toBe("Choose a PDF file.");
    expect(pdfProblem(file("empty.pdf", "application/pdf", 0))).toBe("That file is empty.");
    expect(pdfProblem(file("big.pdf", "application/pdf", MAX_PDF_BYTES + 1))).toBe(
      "That PDF is 50.0 MB; the limit is 50 MB.",
    );
  });
});

describe("formatBytes", () => {
  it("uses KB under a megabyte and MB above", () => {
    expect(formatBytes(200)).toBe("1 KB");
    expect(formatBytes(512 * 1024)).toBe("512 KB");
    expect(formatBytes(3.25 * 1024 * 1024)).toBe("3.3 MB");
  });
});
