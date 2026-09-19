"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { useDepartments, useSharePetition } from "@/lib/api/queries";
import { spacedCode } from "@/lib/petitions";
import { askedLine, notYetAsked, SHARE_IS_AN_ASK } from "@/lib/portal/petitions";

import type { PetitionDepartmentShare } from "@/lib/api/types";

/**
 * The MCE asks a department of the Assembly to answer a petition. It reads as an ask because that is all it is:
 * the note that comes back is the department's own, under the department's name, and this office can neither
 * write it nor change it.
 */

function Asked({ share }: { share: PetitionDepartmentShare }) {
  return (
    <li className="flex flex-col gap-1 border-b pb-3 last:border-0 last:pb-0" data-testid={`mce-petition-asked-${share.department}`}>
      <p className="text-[14.5px] font-medium">{share.department}</p>
      <p className="text-[12.5px] text-ink-soft">{askedLine(share)}</p>
      {share.note ? <p className="text-[14px] whitespace-pre-line">{share.note}</p> : null}
    </li>
  );
}

function ShareForm({ code, shared, onDone }: { code: string; shared: PetitionDepartmentShare[]; onDone: () => void }) {
  const [department, setDepartment] = useState("");
  const departments = useDepartments();
  const share = useSharePetition();
  const left = notYetAsked(departments.data ?? [], shared);
  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      await share.mutateAsync({ code, department });
      toast.success("The department has it. It writes its own note on the petition's page.");
      onDone();
    } catch {
      // share.error is shown on the form
    }
  };
  return (
    <form onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="mce-share-department">The department</Label>
        <NativeSelect id="mce-share-department" value={department} onChange={(e) => setDepartment(e.target.value)}
          required data-testid="mce-share-department">
          <NativeSelectOption value="">Choose a department</NativeSelectOption>
          {left.map((d) => <NativeSelectOption key={d.id} value={d.id}>{d.name}</NativeSelectOption>)}
        </NativeSelect>
      </div>
      <p className="rounded-lg bg-gold-tint px-3 py-2.5 text-[13.5px]">{SHARE_IS_AN_ASK}</p>
      {share.error ? <ErrorNote>{share.error.message}</ErrorNote> : null}
      <DialogFooter>
        <DialogClose asChild>
          <Button type="button" variant="secondary" data-testid="mce-share-cancel">Cancel</Button>
        </DialogClose>
        <Button type="submit" disabled={share.isPending || !department} data-testid="mce-share-confirm">
          Ask the department
        </Button>
      </DialogFooter>
    </form>
  );
}

function ShareDialog({ code, shared }: { code: string; shared: PetitionDepartmentShare[] }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="secondary" className="w-fit" data-testid="mce-share">Ask a department to answer</Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-[20px]">Ask a department about petition {spacedCode(code)}</DialogTitle>
          <DialogDescription>
            The department reads the petition in its own portal and writes one note, published under its name. You
            can&apos;t write that note or change it, and the audit trail keeps yours as the office that asked.
          </DialogDescription>
        </DialogHeader>
        {open ? <ShareForm code={code} shared={shared} onDone={() => setOpen(false)} /> : null}
      </DialogContent>
    </Dialog>
  );
}

export function AskedDepartments({ code, shared }: { code: string; shared: PetitionDepartmentShare[] }) {
  return (
    <>
      {shared.length === 0 ? (
        <p className="text-[14px] text-ink-soft" data-testid="mce-petition-asked-none">
          This petition hasn&apos;t gone to a department yet.
        </p>
      ) : (
        <ul className="flex flex-col gap-3" data-testid="mce-petition-asked">
          {shared.map((share) => <Asked key={share.department} share={share} />)}
        </ul>
      )}
      <ShareDialog code={code} shared={shared} />
    </>
  );
}
