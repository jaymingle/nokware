"use client";

import { CopyIcon, DownloadIcon, MoreHorizontalIcon } from "lucide-react";
import { DropdownMenu } from "radix-ui";
import { useState } from "react";

import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { EXPORT_FAILED, EXPORT_FORMATS, ExportError, NO_SPREADSHEET, downloadAnswer, spreadsheetReady } from "@/lib/ask/export";

import type { ExportFormat, ExportView } from "@/lib/api/types";

const ITEM = "flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-2 text-[14px] outline-none select-none data-disabled:pointer-events-none data-disabled:opacity-50 data-highlighted:bg-muted";

const COPY_FAILED = "The answer couldn't be copied. Select the text and copy it yourself.";

/** Excel is offered only where the answer has report counts or budget figures (see NO_SPREADSHEET). */
function DownloadItems({ view, onPick, testId }: { view: ExportView; onPick: (format: ExportFormat) => void; testId: string }) {
  const sheet = spreadsheetReady(view);
  return (
    <>
      {EXPORT_FORMATS.map(({ format, label }) => {
        const off = format === "xlsx" && !sheet;
        return (
          <DropdownMenu.Item key={format} className={ITEM} disabled={off} data-touch-target
            onSelect={() => onPick(format)} aria-label={off ? `${label}: ${NO_SPREADSHEET}` : `Download this answer as ${label}`}
            data-testid={`${testId}-export-${format}`}>
            <DownloadIcon aria-hidden className="size-3.5 text-ink-soft" />
            {label}
          </DropdownMenu.Item>
        );
      })}
    </>
  );
}

function Menu({ view, onPick, onCopy, testId }: { view: ExportView; onPick: (format: ExportFormat) => void; onCopy: () => void; testId: string }) {
  return (
    <DropdownMenu.Content align="start" sideOffset={6} collisionPadding={12}
      className="z-50 w-[min(19rem,calc(100vw-2rem))] rounded-xl border bg-popover p-1.5 text-popover-foreground">
      <DropdownMenu.Label className="px-2 pt-1 pb-1.5 font-sans text-[12px] font-medium tracking-wide text-ink-soft uppercase">
        Download
      </DropdownMenu.Label>
      <DownloadItems view={view} onPick={onPick} testId={testId} />
      <DropdownMenu.Separator className="my-1.5 h-px bg-hairline" />
      <DropdownMenu.Item className={ITEM} data-touch-target onSelect={onCopy} data-testid={`${testId}-copy`}>
        <CopyIcon aria-hidden className="size-3.5 text-ink-soft" />
        Copy the answer
      </DropdownMenu.Item>
      <p className="px-2 pt-2 pb-1 text-[11.5px] leading-snug text-ink-soft">
        Marked as Nokware&apos;s, not an official AMA document. Downloads are in English, the language of the sources.
        {spreadsheetReady(view) ? "" : " Excel needs report counts or budget figures."}
      </p>
    </DropdownMenu.Content>
  );
}

/** Everything that can be done with an answer except listening to it, which stays out here as a button of its own. */
export function MoreMenu({ view, answer, testId }: { view: ExportView; answer: string; testId: string }) {
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const download = async (format: ExportFormat) => {
    setError(null);
    setNote(`Preparing the ${EXPORT_FORMATS.find((one) => one.format === format)?.label} file…`);
    try {
      await downloadAnswer(view, format);
      setNote(null);
    } catch (failure) {
      setNote(null);
      setError(failure instanceof ExportError ? failure.message : EXPORT_FAILED);
    }
  };
  const copy = () => {
    setError(null);
    navigator.clipboard.writeText(answer).then(() => setNote("Copied"), () => setError(COPY_FAILED));
  };
  return (
    <div className="flex flex-col items-start gap-1.5" data-testid={`${testId}-export`}>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <Button variant="secondary" size="sm" aria-label="More to do with this answer" data-testid={`${testId}-more`}>
            <MoreHorizontalIcon data-icon="inline-start" />
            More
          </Button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <Menu view={view} onPick={download} onCopy={copy} testId={testId} />
        </DropdownMenu.Portal>
      </DropdownMenu.Root>
      <p role="status" className="text-[12.5px] text-ink-soft empty:hidden" data-testid={`${testId}-export-status`}>{note}</p>
      {error ? <ErrorNote testId={`${testId}-export-error`}>{error}</ErrorNote> : null}
    </div>
  );
}
