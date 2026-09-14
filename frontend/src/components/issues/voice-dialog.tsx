"use client";

import { useState, type FormEvent } from "react";

import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useAddVoice } from "@/lib/api/public-queries";
import { joinNames } from "@/lib/text";
import { deviceToken, rememberVoiced } from "@/lib/voices";

import type { Issue, VoiceResult } from "@/lib/api/types";

const NAME_MAX = 80;

function Choice({ checked, onChange, testId, label }: { checked: boolean; onChange: () => void; testId: string; label: string }) {
  return (
    <label className="flex items-center gap-2.5 text-[14px]">
      <input type="radio" name="voice-kind" checked={checked} onChange={onChange} className="size-4 accent-teal" data-testid={testId} />
      {label}
    </label>
  );
}

function NameChoice({ named, setNamed, name, setName, testId }: {
  named: boolean; setNamed: (v: boolean) => void; name: string; setName: (v: string) => void; testId: string;
}) {
  return (
    <fieldset className="flex flex-col gap-2.5">
      <legend className="sr-only">Anonymous or named</legend>
      <Choice checked={!named} onChange={() => setNamed(false)} testId={`${testId}-anonymous`} label="Anonymously" />
      <Choice checked={named} onChange={() => setNamed(true)} testId={`${testId}-named`} label="With my name" />
      {named ? (
        <Input value={name} onChange={(e) => setName(e.target.value)} maxLength={NAME_MAX} required placeholder="Your name"
          aria-label="Your name" autoComplete="name" className="max-w-72" data-testid={`${testId}-name`} />
      ) : null}
    </fieldset>
  );
}

/** The dialog's state: open or not, anonymous or named, and adding the voice. */
function useVoiceForm(issue: Issue, onAdded: (result: VoiceResult) => void) {
  const [open, setOpen] = useState(false);
  const [named, setNamed] = useState(false);
  const [name, setName] = useState("");
  const add = useAddVoice();
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      const result = await add.mutateAsync({ publicId: issue.public_id, deviceToken: deviceToken(), name: named ? name.trim() || null : null });
      rememberVoiced(issue.public_id);
      onAdded(result);
      setOpen(false);
    } catch {
      // add.error is shown in the dialog
    }
  };
  const onOpenChange = (next: boolean) => {
    setOpen(next);
    if (!next) add.reset();
  };
  return { open, onOpenChange, named, setNamed, name, setName, add, submit };
}

/** "This affects me too": anonymous by default, a name only if the resident chooses. Not a petition. */
export function VoiceDialog({ issue, onAdded }: { issue: Issue; onAdded: (result: VoiceResult) => void }) {
  const { open, onOpenChange, named, setNamed, name, setName, add, submit } = useVoiceForm(issue, onAdded);
  const testId = `voice-${issue.public_id}`;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button variant="secondary" size="sm" data-testid={`${testId}-open`}>This affects me too</Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={submit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>This affects me too</DialogTitle>
            <DialogDescription>
              {issue.topic}{issue.ward ? ` in ${issue.ward}` : ""}. Adding your voice tells {joinNames(issue.departments)} how many residents
              this affects.
            </DialogDescription>
          </DialogHeader>
          <NameChoice named={named} setNamed={setNamed} name={name} setName={setName} testId={testId} />
          <p className="text-[12.5px] text-ink-soft">
            A name goes only to the department handling this, and is deleted 30 days after it is closed. This is not a
            signature or a petition: it adds you to a count, and the counts are not verified.
          </p>
          {add.error ? <ErrorNote testId={`${testId}-error`}>{add.error.message}</ErrorNote> : null}
          <DialogFooter>
            <DialogClose asChild>
              <Button type="button" variant="secondary" data-testid={`${testId}-cancel`}>Cancel</Button>
            </DialogClose>
            <Button type="submit" disabled={add.isPending} data-testid={`${testId}-confirm`}>
              {add.isPending ? "Adding…" : "Add my voice"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
