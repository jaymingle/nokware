"use client";

import { CaseDialogFooter, useCaseDialog } from "@/components/cases/case-dialog";
import { FormField } from "@/components/documents/document-fields";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";

import type { CaseDetail, Option } from "@/lib/api/types";
import type { FormEvent } from "react";

// A personal-safety case moves only between these (the server enforces it too).
const SAFETY_RECIPIENTS = new Set(["agency-police", "dept-social-welfare"]);

type ReassignDialogProps = { detail: CaseDetail; recipients: Option[] };

function Choices({ id, label, options }: { id: string; label: string; options: Option[] }) {
  return (
    <FormField id={id} label={label}>
      <NativeSelect id={id} name={id} required defaultValue={options.length === 1 ? options[0].id : ""} className="w-full" data-testid={id}>
        {options.length > 1 ? <NativeSelectOption value="" disabled>Choose…</NativeSelectOption> : null}
        {options.map((option) => (
          <NativeSelectOption key={option.id} value={option.id}>
            {option.name}
          </NativeSelectOption>
        ))}
      </NativeSelect>
    </FormField>
  );
}

function targetsFor(detail: CaseDetail, recipients: Option[]): { current: Option[]; targets: Option[] } {
  const current = detail.assignments.filter((a) => a.active).map((a) => ({ id: a.recipient, name: a.name }));
  const taken = new Set(current.map((c) => c.id));
  const targets = recipients.filter((r) => !taken.has(r.id) && (!detail.private || SAFETY_RECIPIENTS.has(r.id)));
  return { current, targets };
}

/** The MCE moves one recipient's part of a case to another, with a reason for the audit trail. */
export function ReassignDialog({ detail, recipients }: ReassignDialogProps) {
  const dialog = useCaseDialog("Reassigned. The move and your reason are in the audit trail.");
  const { current, targets } = targetsFor(detail, recipients);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const body = { from_recipient: String(form.get("reassign-from")), to_recipient: String(form.get("reassign-to")), reason: String(form.get("reason")).trim() };
    void dialog.run({ id: detail.case_id, action: "reassign", body });
  }

  return (
    <Dialog open={dialog.open} onOpenChange={dialog.onOpenChange}>
      <DialogTrigger asChild>
        <Button variant="secondary" data-testid={`case-reassign-${detail.case_id}`}>Reassign</Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-[20px]">Reassign to another department</DialogTitle>
          <DialogDescription>Case {detail.reference} is with {current.map((c) => c.name).join(" and ")}.</DialogDescription>
        </DialogHeader>
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          {current.length > 1 ? <Choices id="reassign-from" label="Move the part with" options={current} /> : <input type="hidden" name="reassign-from" value={current[0]?.id ?? ""} />}
          <Choices id="reassign-to" label="Move to" options={targets} />
          <FormField id="reassign-reason" label="Reason, written to the audit trail">
            <Input id="reassign-reason" name="reason" required maxLength={2000} placeholder="e.g. drainage works, not refuse collection" data-testid="reassign-reason" />
          </FormField>
          <CaseDialogFooter pending={dialog.pending} error={dialog.error} confirmLabel="Reassign and record" testId="reassign" />
        </form>
      </DialogContent>
    </Dialog>
  );
}
