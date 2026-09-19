"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { usePetitionOptions } from "@/lib/api/petition-queries";
import { useWriteDepartmentNote } from "@/lib/api/queries";
import { NOTE_IS_PUBLIC } from "@/lib/portal/petitions";

/** The officer is told whose name this goes out under before they write a word, not after they have sent it. */
export function PetitionNoteForm({ code }: { code: string }) {
  const [text, setText] = useState("");
  const noteMax = usePetitionOptions().data?.department_note_max;
  const note = useWriteDepartmentNote();
  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    try {
      await note.mutateAsync({ code, text: text.trim() });
      toast.success("Published on the petition's page under your department's name.");
    } catch {
      // note.error is shown under the field
    }
  };
  return (
    <form onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-2.5">
      <Label htmlFor={`note-${code}`}>Your department&apos;s answer</Label>
      <p className="text-[12.5px] text-ink-soft">{NOTE_IS_PUBLIC}</p>
      <Textarea id={`note-${code}`} value={text} onChange={(event) => setText(event.target.value)} required
        maxLength={noteMax} rows={5} data-testid={`shared-petition-${code}-note`} />
      {note.error ? <ErrorNote>{note.error.message}</ErrorNote> : null}
      <Button type="submit" className="w-fit" disabled={note.isPending || text.trim().length === 0}
        data-testid={`shared-petition-${code}-publish`}>
        Publish the note
      </Button>
    </form>
  );
}
