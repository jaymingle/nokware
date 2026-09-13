"use client";

import { useState, type FormEvent, type KeyboardEvent } from "react";
import { ArrowUpIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

export const MAX_QUESTION = 1000;
export const QUESTION_INPUT_ID = "ask-question";
const COUNT_FROM = 900; // show the character count only near the limit

function ComposerHint({ busy, docked, length }: { busy: boolean; docked: boolean; length: number }) {
  const hint = busy ? "Answering your question…" : docked ? "Each question is answered on its own; Nokware doesn't remember earlier ones." : "";
  return (
    <div className={cn("mt-1.5 justify-between gap-3 text-[12px] text-ink-muted", length >= COUNT_FROM ? "flex" : "hidden sm:flex")}>
      <span>{hint}</span>
      {length >= COUNT_FROM ? (
        <span className="tabular-nums" data-testid="ask-count">
          {length}/{MAX_QUESTION}
        </span>
      ) : null}
    </div>
  );
}

type AskComposerProps = { busy: boolean; onAsk: (question: string) => void; docked: boolean; autoFocus?: boolean };

/** The question box: Enter asks, Shift+Enter adds a line. One question at a time. */
function useQuestion(busy: boolean, onAsk: (question: string) => void) {
  const [value, setValue] = useState("");
  const question = value.trim();

  function submit(event?: FormEvent) {
    event?.preventDefault();
    if (!question || busy) return;
    onAsk(question);
    setValue("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) submit(event);
  }

  return { value, setValue, canAsk: Boolean(question) && !busy, submit, onKeyDown };
}

export function AskComposer({ busy, onAsk, docked, autoFocus = false }: AskComposerProps) {
  const { value, setValue, canAsk, submit, onKeyDown } = useQuestion(busy, onAsk);
  return (
    <form
      onSubmit={submit}
      className={cn(docked && "sticky bottom-0 z-10 border-t bg-paper pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]")}
      data-testid="ask-form"
    >
      <label htmlFor={QUESTION_INPUT_ID} className="sr-only">
        Your question
      </label>
      <div className="flex items-end gap-2">
        <Textarea
          id={QUESTION_INPUT_ID}
          autoFocus={autoFocus}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={onKeyDown}
          maxLength={MAX_QUESTION}
          rows={1}
          placeholder={docked ? "Ask another question…" : "Ask about a budget, a fee, a plan or a policy…"}
          className="max-h-40 min-h-11 resize-none py-2.5 text-base md:text-[15px]"
          data-testid="ask-input"
        />
        <Button type="submit" disabled={!canAsk} className="h-11 shrink-0 px-4" data-testid="ask-submit">
          <ArrowUpIcon data-icon="inline-start" />
          Ask
        </Button>
      </div>
      <ComposerHint busy={busy} docked={docked} length={value.length} />
    </form>
  );
}
