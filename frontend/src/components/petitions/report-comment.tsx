"use client";

import { FlagIcon } from "lucide-react";
import { useState } from "react";

import { ErrorNote } from "@/components/documents/panels";
import { ReportGrounds, reportHidesNothing } from "@/components/petitions/report-grounds";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { usePetitionOptions, useReportComment } from "@/lib/api/petition-queries";

import type { PetitionGround, PetitionGroundOption } from "@/lib/api/types";

const FIRST_GROUND: PetitionGround = "private_individual";

type Props = { code: string; commentId: string };

function useCommentReport(code: string, commentId: string) {
  const [ground, setGround] = useState<PetitionGround>(FIRST_GROUND);
  const [note, setNote] = useState("");
  const report = useReportComment(code, commentId);
  const send = () => report.mutate({ ground, note: note.trim() || null });
  const reset = () => {
    report.reset();
    setGround(FIRST_GROUND);
    setNote("");
  };
  return { ground, setGround, note, setNote, report, send, reset };
}

type Report = ReturnType<typeof useCommentReport>;

function Fields({ state, commentId, grounds, noteMax }: {
  state: Report; commentId: string; grounds: PetitionGroundOption[]; noteMax: number;
}) {
  const noteId = `comment-report-note-${commentId}`;
  return (
    <div className="flex flex-col gap-4">
      <ReportGrounds grounds={grounds} chosen={state.ground} onChoose={state.setGround}
        name={`comment-report-${commentId}`} testIdPrefix="comment-report-ground" />
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={noteId}>Anything to add (optional)</Label>
        <Textarea id={noteId} value={state.note} onChange={(e) => state.setNote(e.target.value)} maxLength={noteMax} rows={3}
          autoComplete="off" data-testid="comment-report-note" />
        <p className="text-[12px] text-ink-muted tabular-nums">{state.note.length.toLocaleString()} / {noteMax.toLocaleString()}</p>
      </div>
      {/* The API's own words, as it gave them: it is the only thing that knows why it refused. */}
      {state.report.error ? <ErrorNote testId="comment-report-error">{state.report.error.message}</ErrorNote> : null}
    </div>
  );
}

export function ReportComment({ code, commentId }: Props) {
  const [open, setOpen] = useState(false);
  const options = usePetitionOptions();
  const grounds = options.data?.comment_grounds ?? [];
  const state = useCommentReport(code, commentId);
  const filed = state.report.data !== undefined;
  const close = (next: boolean) => {
    setOpen(next);
    if (!next) state.reset();
  };
  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="sm" className="w-fit text-[12.5px]" data-testid={`comment-report-open-${commentId}`}>
          <FlagIcon data-icon="inline-start" /> Report this comment
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg" data-testid="comment-report-dialog">
        <DialogHeader>
          <DialogTitle className="text-[20px]">Report this comment</DialogTitle>
          <DialogDescription>{reportHidesNothing("comment")} You don&apos;t need to sign in.</DialogDescription>
        </DialogHeader>
        {filed ? (
          <p className="text-[14px]" data-testid="comment-report-filed">{state.report.data?.message}</p>
        ) : (
          <Fields state={state} commentId={commentId} grounds={grounds} noteMax={options.data?.report_note_max ?? 300} />
        )}
        <DialogFooter>
          <Button variant="secondary" onClick={() => close(false)} data-testid="comment-report-close">{filed ? "Done" : "Cancel"}</Button>
          {filed ? null : (
            <Button disabled={state.report.isPending || grounds.length === 0} onClick={state.send} data-testid="comment-report-send">
              {state.report.isPending ? "Sending…" : "Send the report"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
