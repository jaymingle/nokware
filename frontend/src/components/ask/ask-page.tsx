"use client";

import { useCallback, useState } from "react";

import { AskComposer, QUESTION_INPUT_ID } from "@/components/ask/ask-composer";
import { AskTurn } from "@/components/ask/ask-turn";
import { RtiPanel } from "@/components/ask/rti-panel";
import { SuggestedQuestions } from "@/components/ask/suggested-questions";
import { PageIntro } from "@/components/portal/page-intro";
import { useAskThread } from "@/hooks/use-ask-thread";

function RtiFootnote() {
  return (
    <details className="group rounded-xl border bg-card px-5 py-4">
      <summary className="cursor-pointer list-none text-[13.5px] text-ink-soft [&::-webkit-details-marker]:hidden" data-testid="ask-rti-toggle">
        Looking for something the Assembly hasn&apos;t published?{" "}
        <span className="text-teal underline-offset-2 group-hover:underline">You can request it under the RTI Act.</span>
      </summary>
      <div className="mt-4">
        <RtiPanel testId="ask-rti-footnote" />
      </div>
    </details>
  );
}

/** The public Ask page: no sign-in, every answer carries its sources. */
export function AskPage() {
  const { turns, ask, retry, busy } = useAskThread();
  // The question box moves below the answers once there is one; keep typing
  // focus in it, but don't raise a phone keyboard after a tapped suggestion.
  const [keepFocus, setKeepFocus] = useState(false);
  const onAsk = useCallback(
    (question: string) => {
      setKeepFocus(document.activeElement?.id === QUESTION_INPUT_ID);
      const id = ask(question);
      requestAnimationFrame(() => document.getElementById(id)?.scrollIntoView({ block: "start" }));
    },
    [ask],
  );
  const started = turns.length > 0;
  return (
    <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 sm:gap-8">
      <PageIntro eyebrow="Ask Nokware" title="Answers that carry their source">
        Ask about a budget, a fee, a plan or a policy. Every answer names the documents it came from, who published
        them and when. Where the record is silent, Nokware says so.
      </PageIntro>
      {started ? null : (
        <div className="flex flex-col gap-6">
          <AskComposer busy={busy} onAsk={onAsk} docked={false} />
          <SuggestedQuestions onAsk={onAsk} disabled={busy} />
        </div>
      )}
      {turns.map((turn) => (
        <AskTurn key={turn.id} turn={turn} onRetry={retry} />
      ))}
      {started ? <AskComposer busy={busy} onAsk={onAsk} docked autoFocus={keepFocus} /> : null}
      <RtiFootnote />
    </div>
  );
}
