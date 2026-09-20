"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { ErrorNote } from "@/components/documents/panels";
import { ReportGrounds } from "@/components/petitions/report-grounds";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { useRemoveComment } from "@/lib/api/queries";

import type { PetitionGround, PetitionGroundOption } from "@/lib/api/types";

const FIRST_GROUND: PetitionGround = "private_individual";

type Props = { code: string; commentId: string; grounds: PetitionGroundOption[] };

function RemoveForm({ code, commentId, grounds, onDone }: Props & { onDone: () => void }) {
  const [ground, setGround] = useState<PetitionGround>(FIRST_GROUND);
  const remove = useRemoveComment();
  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    remove.mutate({ code, commentId, ground }, {
      onSuccess: () => {
        toast.success("Taken down. The petition and the other comments stand.");
        onDone();
      },
    });
  };
  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <ReportGrounds grounds={grounds} chosen={ground} onChoose={setGround}
        name={`remove-comment-${commentId}`} testIdPrefix={`remove-comment-${commentId}-ground`}
        legend="The ground it comes down on" />
      {remove.error ? <ErrorNote testId={`remove-comment-${commentId}-error`}>{remove.error.message}</ErrorNote> : null}
      <DialogFooter>
        <DialogClose asChild>
          <Button type="button" variant="secondary" data-testid={`remove-comment-${commentId}-cancel`}>Cancel</Button>
        </DialogClose>
        <Button type="submit" disabled={remove.isPending} data-testid={`remove-comment-${commentId}-confirm`}>
          Take this comment down
        </Button>
      </DialogFooter>
    </form>
  );
}

/**
 * No confirmed phone here, unlike a petition's removal: that number proves a contributor neither started nor
 * signed the petition they are judging, and a comment is neither started nor signed.
 */
export function RemoveCommentDialog({ code, commentId, grounds }: Props) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button data-testid={`remove-comment-${commentId}`}>Take it down…</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-[20px]">Take this comment down?</DialogTitle>
          <DialogDescription>
            The ground stands publicly where the words were. The petition stays up, and so does every other comment
            under it. Your name goes in the audit trail, not on the page.
          </DialogDescription>
        </DialogHeader>
        {open ? <RemoveForm code={code} commentId={commentId} grounds={grounds} onDone={() => setOpen(false)} /> : null}
      </DialogContent>
    </Dialog>
  );
}
