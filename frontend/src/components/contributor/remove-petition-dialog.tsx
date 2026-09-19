"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { ErrorNote } from "@/components/documents/panels";
import { PhoneConfirm, PhoneConfirmed } from "@/components/petitions/phone-confirm";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { usePhoneProof } from "@/hooks/use-phone-proof";
import { usePetitionOptions } from "@/lib/api/petition-queries";
import { useRemovePetition } from "@/lib/api/queries";
import { spacedCode } from "@/lib/petitions";
import { groundById, REMOVAL_CONFIRMATION } from "@/lib/portal/petitions";

import type { PetitionGround, PetitionGroundOption } from "@/lib/api/types";

type Draft = { ground: PetitionGround | ""; duplicate: string; note: string };

const EMPTY: Draft = { ground: "", duplicate: "", note: "" };

function GroundChoice({ grounds, draft, change, code }: {
  grounds: PetitionGroundOption[]; draft: Draft; change: (next: Partial<Draft>) => void; code: string;
}) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-[14px] font-medium">The ground</legend>
      {grounds.map((ground) => (
        <label key={ground.id} className="flex items-center gap-2.5 text-[13.5px]">
          <input type="radio" name={`ground-${code}`} value={ground.id} checked={draft.ground === ground.id} required
            onChange={() => change({ ground: ground.id, duplicate: "" })} className="size-4 accent-teal"
            data-testid={`remove-${code}-ground-${ground.id}`} />
          <span>{ground.label}</span>
        </label>
      ))}
    </fieldset>
  );
}

function RemovalFields({ grounds, draft, change, code }: {
  grounds: PetitionGroundOption[]; draft: Draft; change: (next: Partial<Draft>) => void; code: string;
}) {
  const noteMax = usePetitionOptions().data?.removal_note_max;
  const chosen = groundById(grounds, draft.ground);
  return (
    <>
      <GroundChoice grounds={grounds} draft={draft} change={change} code={code} />
      {chosen?.needs_petition_number ? (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`remove-${code}-duplicate`}>The open petition it duplicates (its number)</Label>
          <Input id={`remove-${code}-duplicate`} value={draft.duplicate} onChange={(e) => change({ duplicate: e.target.value })}
            required inputMode="numeric" className="max-w-40" data-testid={`remove-${code}-duplicate`} />
        </div>
      ) : null}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`remove-${code}-note`}>A note for the record (optional)</Label>
        <Textarea id={`remove-${code}-note`} value={draft.note} onChange={(e) => change({ note: e.target.value })}
          maxLength={noteMax} rows={3} data-testid={`remove-${code}-note`} />
        <p className="text-[12.5px] text-ink-soft">
          Kept in the Assembly&apos;s record with your name. Nobody reading the petition&apos;s page sees it, so keep
          personal details out of it.
        </p>
      </div>
    </>
  );
}

function useRemoval(code: string, onDone: () => void) {
  const phone = usePhoneProof();
  const remove = useRemovePetition();
  const send = (draft: Draft) => {
    if (!draft.ground || !phone.proof) return;
    const removal = { ground: draft.ground, duplicate_of: draft.duplicate.trim() || null, note: draft.note.trim() || null };
    remove.mutate({ code, removal, proof: phone.proof.token }, {
      onSuccess: () => {
        toast.success("Removed. Its page now shows the notice giving the ground.");
        onDone();
      },
    });
  };
  return { phone, remove, send };
}

export function RemovePetitionDialog({ code, grounds }: { code: string; grounds: PetitionGroundOption[] }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="destructive" data-testid={`remove-${code}`}>Remove…</Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-[20px]">Remove petition {spacedCode(code)}?</DialogTitle>
          <DialogDescription>
            A petition comes down only on one of these four grounds, and only from a contributor who neither started
            nor signed it. Confirm your number so the server can check that.
          </DialogDescription>
        </DialogHeader>
        {open ? <RemovalForm code={code} grounds={grounds} onDone={() => setOpen(false)} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function ProofStep({ code, phone }: { code: string; phone: ReturnType<typeof usePhoneProof> }) {
  if (phone.proof) return <PhoneConfirmed proof={phone.proof} onForget={phone.forget} />;
  return (
    <PhoneConfirm onConfirmed={phone.confirm}
      lead={`Confirm the number you use here, so the server can check you didn't start or sign petition ${spacedCode(code)}.`} />
  );
}

function RemovalForm({ code, grounds, onDone }: { code: string; grounds: PetitionGroundOption[]; onDone: () => void }) {
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [confirming, setConfirming] = useState(false);
  const { phone, remove, send } = useRemoval(code, onDone);
  const change = (next: Partial<Draft>) => setDraft((current) => ({ ...current, ...next }));
  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (confirming) send(draft);
    else setConfirming(true);
  };
  const chosen = groundById(grounds, draft.ground);
  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      {confirming && chosen ? (
        <div className="flex flex-col gap-3" data-testid={`remove-${code}-confirm-step`}>
          <p className="rounded-lg bg-gold-tint px-3 py-2.5 text-[13.5px]" data-testid={`remove-${code}-ground-chosen`}>
            The ground: <strong className="font-medium">{chosen.label}</strong>
            {draft.duplicate.trim() ? <> · duplicates petition {spacedCode(draft.duplicate.trim())}</> : null}
          </p>
          <p className="text-[14px]">{REMOVAL_CONFIRMATION}</p>
          <ProofStep code={code} phone={phone} />
        </div>
      ) : (
        <RemovalFields grounds={grounds} draft={draft} change={change} code={code} />
      )}
      {remove.error ? <ErrorNote testId={`remove-${code}-error`}>{remove.error.message}</ErrorNote> : null}
      <DialogFooter>
        {confirming ? (
          <Button type="button" variant="secondary" onClick={() => setConfirming(false)} data-testid={`remove-${code}-back`}>Back</Button>
        ) : (
          <DialogClose asChild><Button type="button" variant="secondary" data-testid={`remove-${code}-cancel`}>Cancel</Button></DialogClose>
        )}
        <Button type="submit" variant="destructive" disabled={!draft.ground || remove.isPending || (confirming && !phone.proof)}
          data-testid={`remove-${code}-confirm`}>
          {confirming ? "Remove the petition" : "Continue"}
        </Button>
      </DialogFooter>
    </form>
  );
}
