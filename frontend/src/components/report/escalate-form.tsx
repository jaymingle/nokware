"use client";

import { useState, type FormEvent } from "react";

import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useEscalateReport } from "@/lib/api/public-queries";
import { formatDate } from "@/lib/time";

const NOTE_MAX = 2000;

type EscalateFormProps = { reference: string; until: string; intro: string; action: string };

/** One escalation, within 14 days of the resolution. */
export function EscalateForm({ reference, until, intro, action }: EscalateFormProps) {
  const escalate = useEscalateReport();
  const [note, setNote] = useState("");
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    escalate.mutate({ reference, note: note.trim() });
  };
  return (
    <form onSubmit={submit} className="flex flex-col gap-3 border-t pt-5" data-testid="status-escalate">
      <p className="text-[14px]">
        {intro} You can do this once, until {formatDate(until)}.
      </p>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="escalation-note">What is still wrong?</Label>
        <Textarea id="escalation-note" value={note} onChange={(e) => setNote(e.target.value)} required maxLength={NOTE_MAX}
          autoComplete="off" rows={3} data-testid="status-escalate-note" />
      </div>
      {escalate.error ? <ErrorNote testId="status-escalate-error">{escalate.error.message}</ErrorNote> : null}
      <div>
        <Button type="submit" variant="secondary" disabled={escalate.isPending || !note.trim()} data-testid="status-escalate-submit">
          {escalate.isPending ? "Sending…" : action}
        </Button>
      </div>
    </form>
  );
}
