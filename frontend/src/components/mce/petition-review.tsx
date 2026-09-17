"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { DeadlineNotice } from "@/components/documents/deadline-notice";
import { EmptyPanel, ErrorNote, ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { DocumentLine } from "@/components/petitions/ledger-matches";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useNow } from "@/hooks/use-now";
import { useDecidePetition, usePetitionReview } from "@/lib/api/queries";
import { placeLine, spacedCode, startedBy } from "@/lib/petitions";
import { joinNames } from "@/lib/text";
import { formatDate } from "@/lib/time";

import type { RefusalReason, ReviewItem } from "@/lib/api/types";

const NOTE_MAX = 1000;
const PASSED = "The 72 hours have run out: this petition is being published automatically.";

function useDecision(code: string, onDone: () => void) {
  const decide = useDecidePetition();
  const run = async (decision: Parameters<typeof decide.mutateAsync>[0]["decision"], success: string) => {
    try {
      await decide.mutateAsync({ code, decision });
      toast.success(success);
      onDone();
    } catch {
      // decide.error is shown in the dialog
    }
  };
  return { run, pending: decide.isPending, error: decide.error, reset: decide.reset };
}

function PublishDialog({ item }: { item: ReviewItem }) {
  const [open, setOpen] = useState(false);
  const decision = useDecision(item.code, () => setOpen(false));
  return (
    <Dialog open={open} onOpenChange={(next) => { setOpen(next); if (!next) decision.reset(); }}>
      <DialogTrigger asChild><Button data-testid={`petition-review-${item.code}-publish`}>Publish now</Button></DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-[20px]">Publish this petition?</DialogTitle>
          <DialogDescription>It goes on the public petitions page, open for signatures for 90 days. This can&apos;t be undone.</DialogDescription>
        </DialogHeader>
        {decision.error ? <ErrorNote>{decision.error.message}</ErrorNote> : null}
        <DialogFooter>
          <DialogClose asChild><Button variant="secondary" data-testid={`petition-review-${item.code}-publish-cancel`}>Cancel</Button></DialogClose>
          <Button disabled={decision.pending} onClick={() => void decision.run({ decision: "publish" }, "Published.")}
            data-testid={`petition-review-${item.code}-publish-confirm`}>Publish</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ReasonChoice({ reasons, reason, setReason, code }: { reasons: RefusalReason[]; reason: string; setReason: (r: string) => void; code: string }) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-1 text-[14px] font-medium">The reason</legend>
      {reasons.map((r) => (
        <label key={r.id} className="flex items-start gap-2.5 text-[13.5px]">
          <input type="radio" name="reason" value={r.id} checked={reason === r.id} onChange={() => setReason(r.id)} required
            className="mt-1 size-4 accent-teal" data-testid={`petition-review-${code}-reason-${r.id}`} />
          <span className="flex flex-col"><span>{r.label}</span><span className="text-[12.5px] text-ink-soft">{r.explanation}</span></span>
        </label>
      ))}
    </fieldset>
  );
}

function RefuseForm({ item, reasons, onDone }: { item: ReviewItem; reasons: RefusalReason[]; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const decision = useDecision(item.code, onDone);
  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const note = String(form.get("note") ?? "").trim() || null;
    const duplicate = String(form.get("duplicate") ?? "").trim() || null;
    void decision.run({ decision: "refuse", reason, note, duplicate_of: duplicate }, "Refused. The person who started it sees why on their petitions page.");
  };
  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4">
      <ReasonChoice reasons={reasons} reason={reason} setReason={setReason} code={item.code} />
      {reason === "duplicate" ? (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor={`duplicate-${item.code}`}>The open petition it duplicates (its number)</Label>
          <Input id={`duplicate-${item.code}`} name="duplicate" required inputMode="numeric" className="max-w-40" data-testid={`petition-review-${item.code}-duplicate`} />
        </div>
      ) : null}
      <div className="flex flex-col gap-1.5">
        <Label htmlFor={`note-${item.code}`}>A note to the person who started it (optional)</Label>
        <Textarea id={`note-${item.code}`} name="note" maxLength={NOTE_MAX} rows={3} data-testid={`petition-review-${item.code}-note`} />
        <p className="text-[12.5px] text-ink-soft">They see it; the public doesn&apos;t. The public list counts the refusal under its reason.</p>
      </div>
      {decision.error ? <ErrorNote>{decision.error.message}</ErrorNote> : null}
      <DialogFooter>
        <DialogClose asChild><Button type="button" variant="secondary" data-testid={`petition-review-${item.code}-refuse-cancel`}>Cancel</Button></DialogClose>
        <Button type="submit" variant="destructive" disabled={decision.pending || !reason} data-testid={`petition-review-${item.code}-refuse-confirm`}>Refuse</Button>
      </DialogFooter>
    </form>
  );
}

function RefuseDialog({ item, reasons }: { item: ReviewItem; reasons: RefusalReason[] }) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button variant="destructive" data-testid={`petition-review-${item.code}-refuse`}>Refuse…</Button></DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-[20px]">Refuse this petition?</DialogTitle>
          <DialogDescription>A petition can be refused only for one of these reasons. The person who started it can edit it and send it back.</DialogDescription>
        </DialogHeader>
        {open ? <RefuseForm item={item} reasons={reasons} onDone={() => setOpen(false)} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function Details({ item }: { item: ReviewItem }) {
  return (
    <>
      <p className="text-[12.5px] text-ink-soft">
        No. {spacedCode(item.code)} · {item.topic} · {placeLine(item)} · concerns {joinNames(item.departments)} · {startedBy(item.started_by)} · sent {formatDate(item.submitted_at)}
      </p>
      <h2 className="text-[20px] leading-snug">{item.title}</h2>
      <p className="text-[14.5px] whitespace-pre-line">{item.body}</p>
      {item.issue ? <p className="text-[13px] text-ink-soft">Linked to an open issue: {item.issue.topic}{item.issue.ward ? ` in ${item.issue.ward}` : ""}</p> : null}
      {item.documents.map((doc) => <DocumentLine key={doc.id} doc={doc} />)}
      {item.earlier_refusals.map((r, i) => (
        <p key={i} className="rounded-lg bg-brick-tint px-3 py-2 text-[13px]">
          Refused before: {r.label}. {r.note ? `Your note: “${r.note}” ` : ""}It has since been edited and sent back.
        </p>
      ))}
    </>
  );
}

function ReviewCard({ item, reasons, now }: { item: ReviewItem; reasons: RefusalReason[]; now: number }) {
  const open = Date.parse(item.review_deadline) > now;
  return (
    <Card className="gap-0 py-0" data-testid={`petition-review-${item.code}`}>
      <DeadlineNotice heldUntil={item.review_deadline} unless="you refuse it" passed={PASSED} testId={`petition-review-${item.code}-deadline`} />
      <div className="flex flex-col gap-3 p-5">
        <Details item={item} />
        {open ? <div className="flex flex-wrap gap-2 pt-1"><PublishDialog item={item} /><RefuseDialog item={item} reasons={reasons} /></div> : null}
      </div>
    </Card>
  );
}

/** Refusal only for a fixed reason; silence publishes. */
export function PetitionReview() {
  const now = useNow();
  const { data, error, isPending, refetch } = usePetitionReview();
  if (isPending) return <LoadingPanel label="Loading petitions…" />;
  if (error) return <ErrorPanel message={error.message} onRetry={() => void refetch()} />;
  if (data.petitions.length === 0) {
    return <EmptyPanel title="No petitions waiting for you">When a resident sends a petition, it appears here with the time left before it publishes automatically.</EmptyPanel>;
  }
  return (
    <section aria-label="Petitions waiting for your review" className="flex flex-col gap-4">
      {data.petitions.map((item) => <ReviewCard key={item.code} item={item} reasons={data.refusal_reasons} now={now} />)}
    </section>
  );
}
