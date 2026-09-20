"use client";

import { useState } from "react";

import { ErrorNote } from "@/components/documents/panels";
import { PhoneConfirm, PhoneConfirmed } from "@/components/petitions/phone-confirm";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { usePhoneProof } from "@/hooks/use-phone-proof";
import { useMyPetitions, usePetitionOptions, useReplyToResponse } from "@/lib/api/petition-queries";
import { formatDate } from "@/lib/time";

import type { PetitionDetail, PetitionReplyOut } from "@/lib/api/types";
import type { KeptProof } from "@/lib/petitions";

const ONE_REPLY = "One reply stands under the response. It is published as you write it, under the petition's own name.";

/** The reply as everyone reads it: the petition's name over it, or nobody's where the petition is anonymous. */
export function ReplyGiven({ reply, name }: { reply: PetitionReplyOut; name: string | null }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-lg bg-paper-subtle px-4 py-3" data-testid="petition-reply">
      <p className="text-[14px] font-medium" data-testid="petition-reply-by">
        {name ? `${name}, who started this petition, replied` : "The person who started this petition replied"}
      </p>
      <p className="text-[15px] whitespace-pre-line" data-testid="petition-reply-text">{reply.text}</p>
      <p className="text-[12.5px] text-ink-soft tabular-nums">{formatDate(reply.at)}</p>
    </div>
  );
}

function ReplyForm({ code, proof }: { code: string; proof: string }) {
  const options = usePetitionOptions();
  const max = options.data?.reply_max ?? 1000;
  const [text, setText] = useState("");
  const reply = useReplyToResponse(code);
  return (
    // Nothing is cleared on a refusal: the form goes when the reply is on the page, and only then.
    <form className="flex flex-col gap-1.5" onSubmit={(e) => { e.preventDefault(); reply.mutate({ text, proof }); }}
      data-testid="petition-reply-form">
      <Label htmlFor="petition-reply-text">Your reply to this response</Label>
      <Textarea id="petition-reply-text" value={text} onChange={(e) => setText(e.target.value)} rows={4} maxLength={max}
        autoComplete="off" data-testid="petition-reply-text" />
      <p className="text-[12px] text-ink-muted tabular-nums">{text.length.toLocaleString()} / {max.toLocaleString()}</p>
      <p className="text-[12.5px] text-ink-soft">{ONE_REPLY}</p>
      <Button type="submit" className="mt-1 w-fit" disabled={reply.isPending || !text.trim()} data-testid="petition-reply-send">
        {reply.isPending ? "Publishing your reply…" : "Publish your reply"}
      </Button>
      {reply.error ? <ErrorNote testId="petition-reply-error">{reply.error.message}</ErrorNote> : null}
    </form>
  );
}

/** The same door the creator's other actions go through: their petitions are the ones their number started. */
function Creator({ petition, proof, onForget }: { petition: PetitionDetail; proof: KeptProof; onForget: () => void }) {
  const mine = useMyPetitions(proof.token);
  const isMine = mine.data?.petitions.some((own) => own.code === petition.code) ?? false;
  return (
    <div className="flex flex-col gap-3">
      <PhoneConfirmed proof={proof} onForget={onForget} />
      {mine.isPending ? <p className="text-[13.5px] text-ink-soft" aria-live="polite">Checking this number…</p> : null}
      {mine.error ? <ErrorNote testId="petition-reply-mine-error">{mine.error.message}</ErrorNote> : null}
      {mine.data && !isMine ? (
        <p className="text-[13.5px] text-ink-soft" data-testid="petition-reply-not-yours">
          This number didn&apos;t start this petition. Only the number that did can reply to the response.
        </p>
      ) : null}
      {isMine ? <ReplyForm code={petition.code} proof={proof.token} /> : null}
    </div>
  );
}

/**
 * Only the creator replies, and only once, so the page asks nothing of the thousands who are only reading: it
 * offers, and the number is confirmed when somebody says the petition is theirs.
 */
export function ReplyToResponse({ petition }: { petition: PetitionDetail }) {
  const phone = usePhoneProof();
  const [asked, setAsked] = useState(false);
  if (!phone.ready) return null;
  if (!asked) {
    return (
      <Button variant="ghost" size="sm" className="w-fit" onClick={() => setAsked(true)} data-testid="petition-reply-open">
        I started this petition: reply to this response
      </Button>
    );
  }
  if (!phone.proof) {
    return <PhoneConfirm onConfirmed={phone.confirm} lead="Confirm the number you started this petition with, to reply to this response." />;
  }
  return <Creator petition={petition} proof={phone.proof} onForget={phone.forget} />;
}
