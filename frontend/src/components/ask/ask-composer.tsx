"use client";

import { ArrowUpIcon } from "lucide-react";
import { useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { VoiceCheck, VoiceControl } from "@/components/ask/voice-question";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useVoiceQuestion } from "@/hooks/use-voice-question";
import { cn } from "@/lib/utils";

export const MAX_QUESTION = 1000;
export const QUESTION_INPUT_ID = "ask-question";
const COUNT_FROM = 900; // show the character count only near the limit

function ComposerHint({ busy, panel, length }: { busy: boolean; panel: boolean; length: number }) {
  // A chat suggests memory; Ask has none, so the box says so. In the panel there is room for the short form only.
  // Nobody discovers a language they aren't told about, and this is where a question is typed.
  const memory = panel
    ? "Ask in English, French or Twi. Each question is answered on its own."
    : "Ask in English, French or Twi, and the answer comes back in the language you asked. Each question is answered on its own: Nokware doesn't remember earlier ones.";
  const hint = busy ? "Answering your question…" : memory;
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

type AskComposerProps = { busy: boolean; onAsk: (question: string) => void; started: boolean; panel: boolean };

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

/** A spoken question, checked first: asked as heard, or put in the box to correct. */
function useSpokenQuestion(onAsk: (question: string) => void, setValue: (value: string) => void) {
  const voice = useVoiceQuestion();
  const input = useRef<HTMLTextAreaElement>(null);
  const askHeard = (question: string) => {
    voice.clear();
    onAsk(question);
  };
  const editHeard = (question: string) => {
    voice.clear();
    setValue(question);
    requestAnimationFrame(() => input.current?.focus());
  };
  return { voice, input, askHeard, editHeard };
}

/** The question box, fixed at the bottom of the conversation: docked to the window on the page, the panel's foot in a panel. */
export function AskComposer({ busy, onAsk, started, panel }: AskComposerProps) {
  const { value, setValue, canAsk, submit, onKeyDown } = useQuestion(busy, onAsk);
  const { voice, input, askHeard, editHeard } = useSpokenQuestion(onAsk, setValue);
  return (
    <form
      onSubmit={submit}
      className={cn("border-t bg-paper pt-3", panel ? "px-4 pb-3" : "sticky bottom-0 z-10 pb-[max(0.75rem,env(safe-area-inset-bottom))]")}
      data-testid="ask-form"
    >
      <VoiceCheck state={voice.state} busy={busy} onAsk={askHeard} onEdit={editHeard} onDismiss={voice.clear} onRetry={voice.start} />
      <label htmlFor={QUESTION_INPUT_ID} className="sr-only">
        Your question
      </label>
      <div className="flex items-end gap-2">
        <Textarea
          ref={input}
          id={QUESTION_INPUT_ID}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={onKeyDown}
          maxLength={MAX_QUESTION}
          rows={1}
          placeholder={started ? "Ask another question…" : panel ? "Ask a question…" : "Ask about a budget, a fee, a plan or a policy…"}
          className={cn("max-h-40 min-h-11 resize-none py-2.5 text-base md:text-[15px]", voice.state.kind === "recording" && "hidden")}
          data-testid="ask-input"
        />
        <VoiceControl state={voice.state} onStart={voice.start} onStop={voice.stop} onCancel={voice.cancel} />
        <Button type="submit" disabled={!canAsk} className="h-11 shrink-0 px-4" data-testid="ask-submit">
          <ArrowUpIcon data-icon="inline-start" />
          Ask
        </Button>
      </div>
      <ComposerHint busy={busy} panel={panel} length={value.length} />
    </form>
  );
}
