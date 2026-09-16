import { ArrowRightIcon } from "lucide-react";

import { cn } from "@/lib/utils";

/** Questions the Ledger is known to answer, so a first visit starts somewhere useful. */
const SUGGESTIONS = [
  "How do I get a building permit?",
  "What fees does AMA charge for market stalls?",
  "What does AMA do about flooding?",
  "What are the fines for littering under the bye-laws?",
];

type SuggestedProps = { onAsk: (question: string) => void; disabled: boolean; compact?: boolean };

export function SuggestedQuestions({ onAsk, disabled, compact = false }: SuggestedProps) {
  return (
    <div className="flex flex-col gap-2.5">
      <p className="text-[13px] font-medium text-ink">Try asking</p>
      {/*
        Tinted, with the arrow a link carries. As plain bordered boxes of
        left-aligned text these read as form fields, and the one thing on the
        page a first visitor should press looked like something to type in.
      */}
      <ul className={cn("grid gap-2", !compact && "sm:grid-cols-2")}>
        {SUGGESTIONS.map((question, index) => (
          <li key={question}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onAsk(question)}
              className="group flex w-full cursor-pointer items-center justify-between gap-2 rounded-lg border border-teal/30 bg-teal-tint/50 px-3.5 py-3 text-start text-[14px] font-medium text-ink transition-colors hover:border-teal hover:bg-teal-tint disabled:cursor-not-allowed disabled:opacity-60"
              data-testid={`ask-suggestion-${index}`}
            >
              {question}
              <ArrowRightIcon aria-hidden className="size-4 shrink-0 text-teal transition-transform group-hover:translate-x-0.5" />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
