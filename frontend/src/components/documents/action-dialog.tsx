"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { toast } from "sonner";

import { ErrorNote } from "@/components/documents/panels";
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
import { useDocumentAction, useRefreshDocuments } from "@/lib/api/queries";

import type { DocumentOut, ReviewAction } from "@/lib/api/types";

const NOTE_MAX = 2000;

type Tone = "primary" | "destructive";

type ActionDialogProps = {
  doc: DocumentOut;
  action: ReviewAction;
  triggerLabel: string;
  tone: Tone;
  title: string;
  description: ReactNode;
  confirmLabel: string;
  note?: { label: string; hint: string; required: boolean };
  success: string;
};

function NoteField({ label, hint, required, testId }: NonNullable<ActionDialogProps["note"]> & { testId: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={testId}>{label}</Label>
      <Textarea id={testId} name="note" required={required} maxLength={NOTE_MAX} rows={4} data-testid={testId} />
      <p className="text-[12.5px] text-ink-soft">{hint}</p>
    </div>
  );
}

export function ActionDialog(props: ActionDialogProps) {
  const { doc, action, tone, note } = props;
  const [open, setOpen] = useState(false);
  const mutation = useDocumentAction();
  const refresh = useRefreshDocuments();
  const variant = tone === "destructive" ? "destructive" : "default";
  const testId = `${action}-${doc.id}`;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = String(new FormData(event.currentTarget).get("note") ?? "").trim();
    try {
      await mutation.mutateAsync({ id: doc.id, action, note: text || undefined });
      setOpen(false);
      toast.success(props.success);
    } catch {
      // mutation.error is shown in the dialog
    }
  }

  function onOpenChange(next: boolean) {
    setOpen(next);
    if (next) return;
    // A refused action usually means the document changed elsewhere: show where it stands now.
    if (mutation.isError) void refresh();
    mutation.reset();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant={variant} data-testid={testId}>
          {props.triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-[20px]">{props.title}</DialogTitle>
          <DialogDescription>{props.description}</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          {note ? <NoteField {...note} testId={`${testId}-note`} /> : null}
          {mutation.error ? <ErrorNote>{mutation.error.message}</ErrorNote> : null}
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="secondary" data-testid={`${testId}-cancel`}>
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" variant={variant} disabled={mutation.isPending} data-testid={`${testId}-confirm`}>
              {mutation.isPending ? "Sending…" : props.confirmLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
