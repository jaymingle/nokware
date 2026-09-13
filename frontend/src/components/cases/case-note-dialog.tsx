"use client";

import type { FormEvent, ReactNode } from "react";

import { CaseDialogFooter, useCaseDialog } from "@/components/cases/case-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

import type { CaseAction } from "@/lib/api/types";

const NOTE_MAX = 2000;

export type CaseNoteDialogProps = {
  caseId: string;
  action: Extract<CaseAction, "resolve" | "reopen" | "confirm-resolution">;
  triggerLabel: string;
  title: string;
  description: ReactNode;
  noteLabel: string;
  hint: string;
  confirmLabel: string;
  success: string;
  tone?: "primary" | "secondary";
};

/** A case action that needs a note: resolving, reopening or confirming a resolution. */
export function CaseNoteDialog({ caseId, action, tone = "primary", ...copy }: CaseNoteDialogProps) {
  const dialog = useCaseDialog(copy.success);
  const testId = `case-${action}-${caseId}`;

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const note = String(new FormData(event.currentTarget).get("note") ?? "").trim();
    void dialog.run({ id: caseId, action, body: { note } });
  }

  return (
    <Dialog open={dialog.open} onOpenChange={dialog.onOpenChange}>
      <DialogTrigger asChild>
        <Button variant={tone === "primary" ? "default" : "secondary"} data-testid={testId}>
          {copy.triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-[20px]">{copy.title}</DialogTitle>
          <DialogDescription>{copy.description}</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor={`${testId}-note`}>{copy.noteLabel}</Label>
            <Textarea id={`${testId}-note`} name="note" required maxLength={NOTE_MAX} rows={4} data-testid={`${testId}-note`} />
            <p className="text-[12.5px] text-ink-soft">{copy.hint}</p>
          </div>
          <CaseDialogFooter pending={dialog.pending} error={dialog.error} confirmLabel={copy.confirmLabel} testId={testId} />
        </form>
      </DialogContent>
    </Dialog>
  );
}
