"use client";

import { useState } from "react";

import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { caseNoteCopy } from "@/lib/cases";
import { CASE_NOTE_MAX } from "@/lib/limits";

/** The note being written, emptied whenever the dialog opens or closes so nothing is carried into the next case. */
export function useCaseNote(openChange: (next: boolean) => void) {
  const [note, setNote] = useState("");
  function onOpenChange(next: boolean) {
    setNote("");
    openChange(next);
  }
  return { note, setNote, onOpenChange, missing: note.trim() === "" };
}

type CaseNoteFieldProps = {
  testId: string;
  /** The field the API reads it as: "note" everywhere, "reason" on a reassignment. */
  name: string;
  value: string;
  onChange: (next: string) => void;
  /** A personal-safety case: the note is kept from the resident and said so. */
  internal: boolean;
  required: boolean;
  placeholder?: string;
};

/** The note a stage of a case carries, with its reader named and the limit in sight while it is written. */
export function CaseNoteField({ testId, name, value, onChange, internal, required, placeholder }: CaseNoteFieldProps) {
  const copy = caseNoteCopy(internal);
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={testId}>{copy.label}</Label>
      <Textarea
        id={testId}
        name={name}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required={required}
        maxLength={CASE_NOTE_MAX}
        rows={4}
        placeholder={placeholder}
        aria-describedby={`${testId}-hint`}
        data-testid={testId}
      />
      <p id={`${testId}-hint`} className="text-[12.5px] text-ink-soft">{copy.hint}</p>
      <span className="text-[12px] text-ink-muted tabular-nums" data-testid={`${testId}-count`}>
        {value.length.toLocaleString()} / {CASE_NOTE_MAX.toLocaleString()}
      </span>
    </div>
  );
}
