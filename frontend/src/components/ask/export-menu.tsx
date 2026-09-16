"use client";

import { DownloadIcon } from "lucide-react";
import { useState } from "react";

import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { EXPORT_FAILED, EXPORT_FORMATS, ExportError, NO_SPREADSHEET, downloadAnswer, spreadsheetReady } from "@/lib/ask/export";

import type { ExportFormat, ExportView } from "@/lib/api/types";

/**
 * Download the answer as a PDF, a Word document, a CSV or an Excel workbook. Each says it's Nokware's, not an
 * official AMA document. Excel is offered only where the answer counts residents' reports (see NO_SPREADSHEET).
 */
export function ExportMenu({ view, testId }: { view: ExportView; testId: string }) {
  const [busy, setBusy] = useState<ExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);
  const download = async (format: ExportFormat) => {
    setBusy(format);
    setError(null);
    try {
      await downloadAnswer(view, format);
    } catch (failure) {
      setError(failure instanceof ExportError ? failure.message : EXPORT_FAILED);
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="flex flex-col items-end gap-1.5 max-sm:items-start" data-testid={`${testId}-export`}>
      <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Download this answer">
        <DownloadIcon aria-hidden className="me-1 size-3.5 text-ink-soft" />
        <span className="me-1 text-[13px] text-ink-soft">Download</span>
        {EXPORT_FORMATS.map(({ format, label }) => {
          const off = format === "xlsx" && !spreadsheetReady(view);
          return (
            <Button key={format} variant="ghost" size="xs" className="text-[12.5px] text-teal" disabled={busy !== null || off}
              onClick={() => download(format)} title={off ? NO_SPREADSHEET : undefined}
              aria-label={off ? `${label}: ${NO_SPREADSHEET}` : `Download this answer as ${label}`}
              aria-disabled={off || undefined} data-testid={`${testId}-export-${format}`}>
              {busy === format ? "Preparing…" : label}
            </Button>
          );
        })}
      </div>
      <p className="text-[11.5px] text-ink-soft">
        Marked as Nokware&apos;s, not an official AMA document.
        {spreadsheetReady(view) ? "" : " Excel needs figures Nokware counted itself."}
      </p>
      {error ? <ErrorNote testId={`${testId}-export-error`}>{error}</ErrorNote> : null}
    </div>
  );
}
