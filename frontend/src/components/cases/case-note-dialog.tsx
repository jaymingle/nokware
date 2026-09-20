"use client";

import { CaseDialogFooter, useCaseDialog } from "@/components/cases/case-dialog";
import { CaseNoteField, useCaseNote } from "@/components/cases/case-note-field";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

import type { CaseAction, CaseDetail } from "@/lib/api/types";
import type { FormEvent, ReactNode } from "react";

type CaseNoteDialogProps = {
  detail: CaseDetail;
  action: Exclude<CaseAction, "reassign">;
  triggerLabel: string;
  title: string;
  description: ReactNode;
  /** Resolving can't be sent without a note; the other stages offer one. */
  noteRequired: boolean;
  confirmLabel: string;
  success: string;
  tone?: "primary" | "secondary";
};

export function CaseNoteDialog({ detail, action, tone = "primary", noteRequired, ...copy }: CaseNoteDialogProps) {
  const dialog = useCaseDialog(copy.success);
  const { note, setNote, onOpenChange, missing } = useCaseNote(dialog.onOpenChange);
  const testId = `case-${action}-${detail.case_id}`;

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void dialog.run({ id: detail.case_id, action, body: { note: note.trim() } });
  }

  return (
    <Dialog open={dialog.open} onOpenChange={onOpenChange}>
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
          <CaseNoteField testId={`${testId}-note`} name="note" value={note} onChange={setNote} internal={detail.private} required={noteRequired} />
          <CaseDialogFooter
            pending={dialog.pending}
            error={dialog.error}
            confirmLabel={copy.confirmLabel}
            testId={testId}
            disabled={noteRequired && missing}
          />
        </form>
      </DialogContent>
    </Dialog>
  );
}
