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
      <p className="text-[12.5px] text-ink-soft">Try asking</p>
      <ul className={cn("grid gap-2", !compact && "sm:grid-cols-2")}>
        {SUGGESTIONS.map((question, index) => (
          <li key={question}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onAsk(question)}
              className="w-full cursor-pointer rounded-lg border bg-card px-3.5 py-3 text-start text-[14px] transition-colors hover:border-teal hover:text-teal disabled:cursor-not-allowed disabled:opacity-60"
              data-testid={`ask-suggestion-${index}`}
            >
              {question}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
