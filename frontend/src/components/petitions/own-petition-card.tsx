"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";

import { ErrorNote } from "@/components/documents/panels";
import { DraftFields } from "@/components/petitions/draft-fields";
import { OwnPetitionRecord } from "@/components/petitions/own-petition-record";
import { PetitionImageField, keptImages, type KeptImage } from "@/components/petitions/petition-images";
import { StatusTag } from "@/components/status-tag";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { fromPetition, toRequest } from "@/hooks/use-petition-draft";
import { useChangePetition, useEditPetition, usePetitionOptions } from "@/lib/api/petition-queries";
import { placeLine, removedLine, sendingLabel, spacedCode } from "@/lib/petitions";
import { petitionStatus } from "@/lib/status";

import type { CreatorAction } from "@/lib/api/petitions";
import type { OwnPetition } from "@/lib/api/types";
import type { Sending } from "@/lib/api/upload";
import type { ReportPhoto } from "@/lib/report/photos";

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

/** A petition a contributor took down. Editing it and sending it again is what publishes it back. */
function Removed({ petition }: { petition: OwnPetition }) {
  const removal = petition.removal;
  if (!removal) return null;
  return (
    <div className="flex flex-col gap-1.5 rounded-lg bg-brick-tint px-4 py-3 text-[13.5px]" data-testid={`own-${petition.code}-removal`}>
      <p className="font-medium text-brick">{removedLine({ ground_words: removal.label, removed_at: removal.removed_at })}</p>
      {removal.duplicate_of ? (
        <p>The petition it duplicates: <Link href={`/petitions/${removal.duplicate_of}`} className="text-teal underline">{spacedCode(removal.duplicate_of)}</Link></p>
      ) : null}
      <p className="text-[12.5px] text-ink-soft">Mend the words and publish it again, at this same number.</p>
    </div>
  );
}

function useEdit(petition: OwnPetition, proof: string, onDone: () => void) {
  const [draft, setDraft] = useState(() => fromPetition(petition));
  const [kept, setKept] = useState<KeptImage[]>(() => keptImages(petition.image_ids, petition.images));
  const [added, setAdded] = useState<ReportPhoto[]>([]);
  const [progress, setProgress] = useState<Sending | null>(null);
  const edit = useEditPetition(setProgress);
  const send = async () => {
    setProgress({ sent: 0, total: 1 });
    const words = { words: toRequest(draft), images: added.map((image) => image.file), keepImages: kept.map((image) => image.id) };
    try {
      await edit.mutateAsync({ code: petition.code, edit: words, proof });
      onDone();
    } catch {
      setProgress(null); // edit.error is shown below the fields
    }
  };
  return { draft, setDraft, kept, setKept, added, setAdded, edit, send, progress };
}

function Edit({ petition, proof, onDone }: Props & { onDone: () => void }) {
  const options = usePetitionOptions();
  const state = useEdit(petition, proof, onDone);
  if (!options.data) return null;
  const label = state.edit.isPending ? sendingLabel(state.progress, "Publishing…") : "Publish the new version";
  return (
    <div className="flex flex-col gap-4 border-t pt-4" data-testid={`own-${petition.code}-edit`}>
      <DraftFields draft={state.draft} change={(next) => state.setDraft((d) => ({ ...d, ...next }))} options={options.data}
        testId={`own-${petition.code}-draft`} />
      <PetitionImageField kept={state.kept} onKept={state.setKept} added={state.added} onAdded={state.setAdded} max={options.data.max_images} />
      {state.edit.error ? <ErrorNote>{state.edit.error.message}</ErrorNote> : null}
      <div className="flex flex-wrap items-center gap-2">
        <Button onClick={() => void state.send()} disabled={state.edit.isPending} data-testid={`own-${petition.code}-send`}>{label}</Button>
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
      {can.has("edit") ? <Button size="sm" onClick={onEdit} data-testid={`own-${petition.code}-edit-start`}>Edit the words</Button> : null}
      {can.has("make_anonymous") ? (
        <Confirm petition={petition} proof={proof} action="anonymous" trigger="Take my name off" title="Take your name off?"
          description="The petition will say “Started by a resident”. You can't put your name back." confirm="Take it off" />
      ) : null}
      {can.has("withdraw") ? (
        <Confirm petition={petition} proof={proof} action="withdraw" trigger="Close it" title="Close this petition?"
          description="It stays public with the signatures it has, and takes no more. You can't reopen it." confirm="Close it" />
      ) : null}
    </div>
  );
}

export function OwnPetitionCard({ petition, proof }: Props) {
  const [editing, setEditing] = useState(false);
  const tag = petitionStatus(petition.status);
  return (
    <Card className="gap-0 py-0" data-testid={`own-${petition.code}`}>
      <div className="flex flex-col gap-3 p-5">
        <p className="text-[12.5px] text-ink-soft">No. {spacedCode(petition.code)} · {petition.topic} · {placeLine(petition)}</p>
        <h2 className="text-[18px] leading-snug">{petition.title}</h2>
        <div><StatusTag tone={tag.tone} testId={`own-${petition.code}-status`}>{tag.label}</StatusTag></div>
        <Removed petition={petition} />
        {petition.started_by ? <p className="text-[13px] text-ink-soft">Your name is shown publicly: {petition.started_by}</p> : null}
        {editing ? <Edit petition={petition} proof={proof} onDone={() => setEditing(false)} /> : <Actions petition={petition} proof={proof} onEdit={() => setEditing(true)} />}
        {editing ? null : <OwnPetitionRecord code={petition.code} proof={proof} />}
      </div>
    </Card>
  );
}
