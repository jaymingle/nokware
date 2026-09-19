"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { useDismissReport } from "@/lib/api/queries";

import type { PetitionDismissal, PetitionDismissalOption } from "@/lib/api/types";

function ReasonChoice({ reasons, reason, choose, id }: {
  reasons: PetitionDismissalOption[]; reason: PetitionDismissal | ""; choose: (next: PetitionDismissal) => void; id: string;
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-[14px] font-medium">Why you&apos;re settling it</legend>
      {reasons.map((option) => (
        <label key={option.id} className="flex items-center gap-2.5 text-[13.5px]">
          <input type="radio" name={`dismiss-${id}`} value={option.id} checked={reason === option.id} required
            onChange={() => choose(option.id)} className="size-4 accent-teal" data-testid={`dismiss-${id}-reason-${option.id}`} />
          <span>{option.label}</span>
        </label>
      ))}
    </fieldset>
  );
}

function DismissForm({ id, reasons, onDone }: { id: string; reasons: PetitionDismissalOption[]; onDone: () => void }) {
  const [reason, setReason] = useState<PetitionDismissal | "">("");
  const dismiss = useDismissReport();
  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!reason) return;
    dismiss.mutate({ reportId: id, reason }, {
      onSuccess: () => {
        toast.success("Settled. The petition stays exactly as it is.");
        onDone();
      },
    });
  };
  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <ReasonChoice reasons={reasons} reason={reason} choose={setReason} id={id} />
      {dismiss.error ? <ErrorNote testId={`dismiss-${id}-error`}>{dismiss.error.message}</ErrorNote> : null}
      <DialogFooter>
        <DialogClose asChild><Button type="button" variant="secondary" data-testid={`dismiss-${id}-cancel`}>Cancel</Button></DialogClose>
        <Button type="submit" disabled={!reason || dismiss.isPending} data-testid={`dismiss-${id}-confirm`}>Settle this report</Button>
      </DialogFooter>
    </form>
  );
}

/** The other half of the queue: the report is settled on a fixed reason and the petition is left alone. */
export function DismissReportDialog({ id, reasons }: { id: string; reasons: PetitionDismissalOption[] }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="secondary" data-testid={`dismiss-${id}`}>Leave it up…</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-[20px]">Leave this petition up?</DialogTitle>
          <DialogDescription>
            This settles the report and takes it off the queue. The petition is untouched, and whoever reported it
            isn&apos;t told. Anyone can report it again.
          </DialogDescription>
        </DialogHeader>
        {open ? <DismissForm id={id} reasons={reasons} onDone={() => setOpen(false)} /> : null}
      </DialogContent>
    </Dialog>
  );
}
