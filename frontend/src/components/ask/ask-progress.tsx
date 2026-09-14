import { CheckIcon, LoaderCircleIcon } from "lucide-react";

import { cn } from "@/lib/utils";

import type { Turn } from "@/lib/ask/turn";

const TITLES_SHOWN = 3;

function foundSummary(titles: string[]): string {
  if (titles.length === 0) return "No matching documents.";
  const shown = titles.slice(0, TITLES_SHOWN).join("; ");
  const more = titles.length - TITLES_SHOWN;
  return more > 0 ? `${shown}; and ${more} more` : shown;
}

function Step({ state, label, detail }: { state: "active" | "done" | "waiting"; label: string; detail?: string }) {
  return (
    <li className="flex items-start gap-2.5">
      <span aria-hidden className="mt-0.5 grid size-4.5 shrink-0 place-items-center">
        {state === "done" ? <CheckIcon className="size-4 text-teal" /> : null}
        {state === "active" ? <LoaderCircleIcon className="size-4 text-teal motion-safe:animate-spin" /> : null}
        {state === "waiting" ? <span className="size-1.5 rounded-full bg-hairline" /> : null}
      </span>
      <div className="min-w-0">
        <p className={cn("text-[14px]", state === "waiting" ? "text-ink-muted" : "text-ink")}>{label}</p>
        {detail ? <p className="text-[12.5px] break-words text-ink-soft">{detail}</p> : null}
      </div>
    </li>
  );
}

function foundLabel(turn: Turn): string {
  const found = turn.documents.length;
  const counted = turn.figures.length;
  const documents = `Found ${found} ${found === 1 ? "document" : "documents"}`;
  return counted ? `${documents} and counted ${counted} live ${counted === 1 ? "figure" : "figures"}` : documents;
}

/** Real progress from the stream: the search (and any counting), what it found, then the writing. */
export function AskProgress({ turn, testId }: { turn: Turn; testId: string }) {
  const searching = turn.stage === "searching" || turn.stage === "counting";
  const lookingFor = turn.stage === "counting" ? "Searching the Ledger and counting reports" : "Searching the Ledger";
  const status = searching ? lookingFor : "Writing the answer";
  return (
    <div className="flex flex-col gap-3 rounded-xl border bg-paper-subtle px-4 py-3.5" data-testid={testId} data-stage={turn.stage}>
      <p className="sr-only" aria-live="polite">
        {searching ? `${status}…` : `${foundLabel(turn)}. ${status}…`}
      </p>
      <ol className="flex flex-col gap-2.5">
        <Step
          state={searching ? "active" : "done"}
          label={searching ? `${lookingFor}…` : foundLabel(turn)}
          detail={searching ? undefined : foundSummary(turn.documents.map((doc) => doc.title))}
        />
        <Step state={searching ? "waiting" : "active"} label="Writing the answer…" />
      </ol>
      <p className="text-[12px] text-ink-muted">Answers usually take 6 to 13 seconds.</p>
    </div>
  );
}
