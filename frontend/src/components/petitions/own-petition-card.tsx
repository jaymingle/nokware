"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";

import { DeadlineLine } from "@/components/documents/deadline-notice";
import { ErrorNote } from "@/components/documents/panels";
import { DraftFields } from "@/components/petitions/draft-fields";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { fromPetition, toRequest } from "@/hooks/use-petition-draft";
import { useChangePetition, usePetitionOptions } from "@/lib/api/petition-queries";
import { placeLine, spacedCode, STATUS_LABELS } from "@/lib/petitions";

import type { CreatorAction } from "@/lib/api/petitions";
import type { OwnPetition } from "@/lib/api/types";

type Props = { petition: OwnPetition; proof: string };

function Confirm({ petition, proof, action, trigger, title, description, confirm }: Props & {
  action: CreatorAction; trigger: string; title: string; description: ReactNode; confirm: string;
}) {
  const [open, setOpen] = useState(false);
  const change = useChangePetition();
  const run = async () => {
    try {
      await change.mutateAsync({ code: petition.code, proof, action });
      setOpen(false);
    } catch {
      // change.error is shown in the dialog
    }
  };
  const testId = `own-${petition.code}-${action}`;
  return (
    <Dialog open={open} onOpenChange={(next) => { setOpen(next); if (!next) change.reset(); }}>
      <DialogTrigger asChild><Button variant="secondary" size="sm" data-testid={testId}>{trigger}</Button></DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-[20px]">{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        {change.error ? <ErrorNote>{change.error.message}</ErrorNote> : null}
        <DialogFooter>
          <DialogClose asChild><Button variant="secondary" data-testid={`${testId}-cancel`}>Cancel</Button></DialogClose>
          <Button variant="destructive" disabled={change.isPending} onClick={() => void run()} data-testid={`${testId}-confirm`}>{confirm}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Refused({ petition }: { petition: OwnPetition }) {
  const refusal = petition.refusal;
  if (!refusal) return null;
  return (
    <div className="flex flex-col gap-1.5 rounded-lg bg-brick-tint px-4 py-3 text-[13.5px]" data-testid={`own-${petition.code}-refusal`}>
      <p className="font-medium text-brick">Refused: {refusal.label}</p>
      <p>{refusal.explanation}</p>
      {refusal.duplicate_of ? <p>The open petition: <Link href={`/petitions/${refusal.duplicate_of}`} className="text-teal underline">{spacedCode(refusal.duplicate_of)}</Link></p> : null}
      {refusal.note ? <p><span className="text-ink-soft">The MCE&apos;s note to you:</span> {refusal.note}</p> : null}
      <p className="text-[12.5px] text-ink-soft">
        {petition.resubmissions_left > 0 ? `You can edit it and send it back ${petition.resubmissions_left === 1 ? "once more" : `${petition.resubmissions_left} more times`}.` : "It can't be sent back again."}
      </p>
    </div>
  );
}

function Resubmit({ petition, proof, onDone }: Props & { onDone: () => void }) {
  const options = usePetitionOptions();
  const [draft, setDraft] = useState(() => fromPetition(petition));
  const change = useChangePetition();
  const send = async () => {
    try {
      await change.mutateAsync({ code: petition.code, proof, draft: toRequest(draft) });
      onDone();
    } catch {
      // change.error is shown below
    }
  };
  if (!options.data) return null;
  return (
    <div className="flex flex-col gap-4 border-t pt-4" data-testid={`own-${petition.code}-edit`}>
      <DraftFields draft={draft} change={(next) => setDraft((d) => ({ ...d, ...next }))} options={options.data} testId={`own-${petition.code}-draft`} />
      {change.error ? <ErrorNote>{change.error.message}</ErrorNote> : null}
      <div className="flex gap-2">
        <Button onClick={() => void send()} disabled={change.isPending} data-testid={`own-${petition.code}-send`}>Send it back for review</Button>
        <Button variant="ghost" onClick={onDone} data-testid={`own-${petition.code}-edit-cancel`}>Cancel</Button>
      </div>
    </div>
  );
}

function Actions({ petition, proof, onEdit }: Props & { onEdit: () => void }) {
  const can = new Set(petition.actions);
  return (
    <div className="flex flex-wrap gap-2">
      {petition.published_at ? <Button asChild variant="secondary" size="sm"><Link href={`/petitions/${petition.code}`} data-testid={`own-${petition.code}-public`}>See the public page</Link></Button> : null}
      {can.has("resubmit") ? <Button size="sm" onClick={onEdit} data-testid={`own-${petition.code}-resubmit`}>Edit and send back</Button> : null}
      {can.has("make_anonymous") ? (
        <Confirm petition={petition} proof={proof} action="anonymous" trigger="Take my name off" title="Take your name off?"
          description="The petition will say “Started by a resident”. You can't put your name back." confirm="Take it off" />
      ) : null}
      {can.has("withdraw") ? (
        <Confirm petition={petition} proof={proof} action="withdraw" trigger="Withdraw" title="Withdraw this petition?"
          description="It closes for good. If it was published, the page stays up and says you withdrew it." confirm="Withdraw it" />
      ) : null}
    </div>
  );
}

/** One of the creator's own petitions: where it stands, why it was refused, and what they can still do. */
export function OwnPetitionCard({ petition, proof }: Props) {
  const [editing, setEditing] = useState(false);
  return (
    <Card className="gap-0 py-0" data-testid={`own-${petition.code}`}>
      <div className="flex flex-col gap-3 p-5">
      <p className="text-[12.5px] text-ink-soft">No. {spacedCode(petition.code)} · {petition.topic} · {placeLine(petition)}</p>
      <h2 className="text-[18px] leading-snug">{petition.title}</h2>
      <p className="text-[13.5px] font-medium" data-testid={`own-${petition.code}-status`}>{STATUS_LABELS[petition.status]}</p>
      {petition.status === "in_review" && petition.review_deadline ? (
        <DeadlineLine heldUntil={petition.review_deadline} unless="the MCE refuses it" testId={`own-${petition.code}-deadline`} />
      ) : null}
      <Refused petition={petition} />
      {petition.started_by ? <p className="text-[13px] text-ink-soft">Your name is shown publicly: {petition.started_by}</p> : null}
      {editing ? <Resubmit petition={petition} proof={proof} onDone={() => setEditing(false)} /> : <Actions petition={petition} proof={proof} onEdit={() => setEditing(true)} />}
      </div>
    </Card>
  );
}
