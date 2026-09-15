"use client";

import { DownloadIcon } from "lucide-react";
import { useState } from "react";

import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { EXPORT_FAILED, EXPORT_FORMATS, ExportError, downloadAnswer } from "@/lib/ask/export";

import type { ExportFormat, ExportView } from "@/lib/api/types";

/** Download the answer as a PDF, a Word document or a CSV. Each says it's Nokware's, not an official AMA document. */
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
        {EXPORT_FORMATS.map(({ format, label }) => (
          <Button key={format} variant="ghost" size="xs" className="text-[12.5px] text-teal" disabled={busy !== null} onClick={() => download(format)}
            aria-label={`Download this answer as ${label}`} data-testid={`${testId}-export-${format}`}>
            {busy === format ? "Preparing…" : label}
          </Button>
        ))}
      </div>
      <p className="text-[11.5px] text-ink-soft">Marked as Nokware&apos;s, not an official AMA document.</p>
      {error ? <ErrorNote testId={`${testId}-export-error`}>{error}</ErrorNote> : null}
    </div>
  );
}
