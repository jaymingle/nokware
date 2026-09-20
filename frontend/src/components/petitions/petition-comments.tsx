"use client";

import { useState } from "react";

import { ErrorNote } from "@/components/documents/panels";
import { NameChoice } from "@/components/petitions/name-choice";
import { PhoneConfirm, PhoneConfirmed } from "@/components/petitions/phone-confirm";
import { ReportComment } from "@/components/petitions/report-comment";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { usePhoneProof, type PhoneProof } from "@/hooks/use-phone-proof";
import { useAddComment, usePetitionComments, usePetitionOptions } from "@/lib/api/petition-queries";
import { formatDate } from "@/lib/time";

import type { PetitionComment } from "@/lib/api/types";
import type { KeptProof } from "@/lib/petitions";

const HOW_COMMENTS_WORK =
  "A comment is published as you write it: nobody approves it. One confirmed Ghanaian number, as a signature is, and the number itself is never shown.";

const COMMENT_NAME_NOTE =
  "If you show your name, anyone reading this petition can see it over your comment. If you stay anonymous, it stands as “Resident”. A comment can't be changed once it is published.";

function countLine(total: number): string {
  if (total === 0) return "No comments yet.";
  return total === 1 ? "1 comment, newest first." : `${total.toLocaleString()} comments, newest first.`;
}

function When({ at }: { at: string }) {
  return <span className="text-[12.5px] text-ink-soft tabular-nums">{formatDate(at)}</span>;
}

/** A comment a contributor took down: the ground stands where its words were, and nobody's name over it. */
function TakenDown({ comment }: { comment: PetitionComment }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1" data-testid="petition-comment-removed">
      <p className="text-[13.5px] text-ink-soft">{comment.text}</p>
      <When at={comment.at} />
    </div>
  );
}

function Written({ code, comment }: { code: string; comment: PetitionComment }) {
  return (
    <>
      <p className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        <span className="text-[14px] font-medium">{comment.name}</span>
        <When at={comment.at} />
      </p>
      <p className="text-[14.5px] whitespace-pre-line">{comment.text}</p>
      <ReportComment code={code} commentId={comment.id} />
    </>
  );
}

function CommentLine({ code, comment }: { code: string; comment: PetitionComment }) {
  return (
    <li className="flex flex-col items-start gap-1 border-b border-dashed py-3 last:border-b-0" data-testid={`petition-comment-${comment.id}`}>
      {comment.removed ? <TakenDown comment={comment} /> : <Written code={code} comment={comment} />}
    </li>
  );
}

function useCommenting(code: string, phone: PhoneProof) {
  const [text, setText] = useState("");
  const [named, setNamed] = useState(false);
  const [name, setName] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [missingName, setMissingName] = useState(false);
  const add = useAddComment(code);
  const send = (proof: string) => add.mutate({ comment: { text, name: named ? name.trim() : null }, proof }, {
    onSuccess: () => setText(""), // a refusal keeps what they typed; only a published comment clears the field
  });
  const onConfirmed = (proof: KeptProof) => {
    phone.confirm(proof);
    setConfirming(false);
    send(proof.token);
  };
  const start = () => {
    const missing = named && !name.trim();
    setMissingName(missing); // asked before the number is confirmed, not after
    if (missing) return;
    if (phone.proof) send(phone.proof.token);
    else setConfirming(true);
  };
  return { text, setText, named, setNamed, name, setName, confirming, missingName, add, onConfirmed, start };
}

function Fields({ state }: { state: ReturnType<typeof useCommenting> }) {
  // The API owns the limit and refuses anything longer in its own words; the box only keeps a writer inside it.
  const limit = usePetitionOptions().data?.comment_max;
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor="petition-comment-text">Add your comment</Label>
      <Textarea id="petition-comment-text" value={state.text} onChange={(e) => state.setText(e.target.value)} rows={4}
        maxLength={limit} autoComplete="off" data-testid="petition-comment-text" />
      {limit ? (
        <p className="text-[12px] text-ink-muted tabular-nums">{state.text.length.toLocaleString()} / {limit.toLocaleString()}</p>
      ) : null}
    </div>
  );
}

function AddComment({ code, phone }: { code: string; phone: PhoneProof }) {
  const state = useCommenting(code, phone);
  return (
    <div className="flex flex-col gap-4 rounded-lg border bg-paper-subtle px-4 py-4">
      {/* Its own form, so this name choice and the sign panel's are two groups of radios rather than one. */}
      <form className="flex flex-col gap-4" onSubmit={(e) => { e.preventDefault(); state.start(); }} data-testid="petition-comment-form">
        <Fields state={state} />
        <NameChoice named={state.named} setNamed={state.setNamed} name={state.name} setName={state.setName}
          testId="petition-comment-name" anonymousHint="Your comment stands as “Resident”." note={COMMENT_NAME_NOTE} />
        {state.confirming ? null : (
          <Button type="submit" className="w-fit" disabled={state.add.isPending || !state.text.trim()} data-testid="petition-comment-send">
            {state.add.isPending ? "Adding your comment…" : "Add your comment"}
          </Button>
        )}
        {state.missingName ? <ErrorNote testId="petition-comment-missing-name">Enter the name to show, or choose to stay anonymous.</ErrorNote> : null}
        {state.add.error ? <ErrorNote testId="petition-comment-error">{state.add.error.message}</ErrorNote> : null}
      </form>
      {phone.proof && !state.confirming ? <PhoneConfirmed proof={phone.proof} onForget={phone.forget} /> : null}
      {state.confirming ? (
        <PhoneConfirm onConfirmed={state.onConfirmed} lead="Confirm your number to comment. Your comment is published as soon as it's confirmed." />
      ) : null}
    </div>
  );
}

/** What residents have said under the petition, and the field to say something. */
export function PetitionComments({ code }: { code: string }) {
  const phone = usePhoneProof();
  const comments = usePetitionComments(code);
  const pages = comments.data?.pages ?? [];
  const total = pages[0]?.total ?? 0;
  return (
    <section className="flex flex-col gap-3 rounded-xl border bg-card p-5" data-testid="petition-comments">
      <h2 className="text-[19px]">What residents say</h2>
      <p className="text-[13.5px] text-ink-soft" data-testid="petition-comments-count">{countLine(total)} {HOW_COMMENTS_WORK}</p>
      {comments.isPending ? <p className="text-[13.5px] text-ink-soft" aria-live="polite">Loading the comments…</p> : null}
      {comments.error ? <ErrorNote testId="petition-comments-error">{comments.error.message}</ErrorNote> : null}
      {total > 0 ? (
        <ul className="flex flex-col">
          {pages.flatMap((page) => page.comments).map((comment) => <CommentLine key={comment.id} code={code} comment={comment} />)}
        </ul>
      ) : null}
      {comments.hasNextPage ? (
        <Button variant="secondary" size="sm" className="w-fit" disabled={comments.isFetchingNextPage}
          onClick={() => void comments.fetchNextPage()} data-testid="petition-comments-more">
          Show more comments
        </Button>
      ) : null}
      {phone.ready ? <AddComment code={code} phone={phone} /> : null}
    </section>
  );
}
