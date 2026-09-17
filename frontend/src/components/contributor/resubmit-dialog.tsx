"use client";

import { useState } from "react";
import { toast } from "sonner";

import { ErrorNote } from "@/components/documents/panels";
import { PdfField } from "@/components/documents/pdf-field";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { usePdfForm } from "@/hooks/use-pdf-form";
import { useRefreshDocuments, useResubmit } from "@/lib/api/queries";

import type { DocumentOut } from "@/lib/api/types";

const NOTE_MAX = 2000;

type ResubmitFormProps = { doc: DocumentOut; resubmit: ReturnType<typeof useResubmit>; onDone: () => void };

function ResubmitForm({ doc, resubmit, onDone }: ResubmitFormProps) {
  const { file, chooseFile, fileMissing, onSubmit } = usePdfForm(async (form) => {
    const updated = await resubmit.mutateAsync({ id: doc.id, form });
    onDone();
    toast.success(`Resubmitted. ${doc.department_name ?? "The department"} has 72 hours to review it.`);
    return updated;
  });
  const testId = `resubmit-${doc.id}`;
  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <PdfField file={file} onChange={chooseFile} testId={`${testId}-file`} />
      {fileMissing ? <ErrorNote>Choose the revised PDF.</ErrorNote> : null}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`${testId}-note`}>What did you change? (optional)</Label>
        <Textarea id={`${testId}-note`} name="note" maxLength={NOTE_MAX} rows={3} data-testid={`${testId}-note`} />
      </div>
      {resubmit.error ? <ErrorNote>{resubmit.error.message}</ErrorNote> : null}
      <DialogFooter>
        <DialogClose asChild>
          <Button variant="secondary" data-testid={`${testId}-cancel`}>
            Cancel
          </Button>
        </DialogClose>
        <Button type="submit" disabled={resubmit.isPending} data-testid={`${testId}-confirm`}>
          {resubmit.isPending ? "Sending…" : "Resubmit"}
        </Button>
      </DialogFooter>
    </form>
  );
}

export function ResubmitDialog({ doc }: { doc: DocumentOut }) {
  const [open, setOpen] = useState(false);
  const resubmit = useResubmit();
  const refresh = useRefreshDocuments();
  const department = doc.department_name ?? "the department";

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (next) return;
    if (resubmit.isError) void refresh(); // the document may have changed elsewhere
    resubmit.reset();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant="secondary" data-testid={`resubmit-${doc.id}`}>
          Resubmit a corrected version
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-[20px]">Resubmit a corrected version</DialogTitle>
          <DialogDescription>
            You can do this once. It goes back to {department} with a new 72-hour clock, alongside their dispute and
            your note.
          </DialogDescription>
        </DialogHeader>
        {open ? <ResubmitForm doc={doc} resubmit={resubmit} onDone={() => onOpenChange(false)} /> : null}
      </DialogContent>
    </Dialog>
  );
}
