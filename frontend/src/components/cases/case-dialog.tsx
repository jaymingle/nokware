"use client";

import { useState } from "react";
import { toast } from "sonner";

import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { DialogClose, DialogFooter } from "@/components/ui/dialog";
import { useCaseAction, type CaseActionInput } from "@/lib/api/queries";

export function useCaseDialog(success: string) {
  const [open, setOpen] = useState(false);
  const mutation = useCaseAction();

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (!next) mutation.reset();
  }

  async function run(input: CaseActionInput) {
    try {
      await mutation.mutateAsync(input);
      setOpen(false);
      toast.success(success);
    } catch {
      // mutation.error is shown in the dialog
    }
  }

  return { open, onOpenChange, run, pending: mutation.isPending, error: mutation.error };
}

/** disabled: a stage that requires a note has none yet, so there is nothing to send. */
type FooterProps = { pending: boolean; error: Error | null; confirmLabel: string; testId: string; disabled?: boolean };

export function CaseDialogFooter({ pending, error, confirmLabel, testId, disabled = false }: FooterProps) {
  return (
    <>
      {error ? <ErrorNote>{error.message}</ErrorNote> : null}
      <DialogFooter>
        <DialogClose asChild>
          <Button variant="secondary" data-testid={`${testId}-cancel`}>
            Cancel
          </Button>
        </DialogClose>
        <Button type="submit" disabled={pending || disabled} data-testid={`${testId}-confirm`}>
          {pending ? "Saving…" : confirmLabel}
        </Button>
      </DialogFooter>
    </>
  );
}
