"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AnswerChart } from "@/components/ask/answer-chart";
import { AnswerSources } from "@/components/ask/answer-sources";
import { AnswerText } from "@/components/ask/answer-text";
import { AskProgress } from "@/components/ask/ask-progress";
import { ExportMenu } from "@/components/ask/export-menu";
import { FigureCard } from "@/components/ask/figure-card";
import { NoInformation } from "@/components/ask/no-information";
import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { DISAGREEMENT_LEAD } from "@/lib/ask/sources";
import { citedDocuments, type Turn } from "@/lib/ask/turn";

const HIGHLIGHT_MS = 2400;

/** Jumping from a citation to its source: scroll, focus, and briefly highlight the card. */
function useSourceJump(turnId: string) {
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  const anchorFor = useCallback((label: string) => `${turnId}-${label}`, [turnId]);
  const jump = useCallback(
    (label: string) => {
      const card = document.getElementById(anchorFor(label));
      if (!card) return;
      const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      card.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "center" });
      card.focus({ preventScroll: true });
      setHighlighted(label);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setHighlighted(null), HIGHLIGHT_MS);
    },
    [anchorFor],
  );
  return { highlighted, anchorFor, jump };
}

function plural(count: number, one: string, many: string): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** What the answer rests on: documents, live report figures, or both, said apart. */
function Attribution({ documents, figures }: { documents: number; figures: number }) {
  const parts = [
    documents ? `${plural(documents, "document", "documents")} in the Ledger` : null,
    figures ? `${plural(figures, "live report figure", "live report figures")}` : null,
  ].filter(Boolean);
  if (parts.length === 0) return null;
  return (
    <p className="flex items-center gap-2 text-[12.5px] text-ink-soft" data-testid="ask-attribution">
      <span aria-hidden className="size-1.5 rounded-full bg-teal" />
      Answered from {parts.join(" and ")}
    </p>
  );
}

function AnswerFigures({ turn, anchorFor, highlighted, testId }: {
  turn: Turn; anchorFor: (label: string) => string; highlighted: string | null; testId: string;
}) {
  const cited = turn.figures.filter((figure) => figure.cited);
  if (cited.length === 0) return null;
  return (
    <section aria-label="Figures" className="flex flex-col gap-3">
      <h3 className="text-[12.5px] font-medium tracking-wide text-ink-soft uppercase">Figures</h3>
      {cited.map((figure) => (
        <FigureCard key={figure.label} figure={figure} anchorId={anchorFor(figure.label)} highlighted={highlighted === figure.label} testIdPrefix={testId} />
      ))}
    </section>
  );
}

function Disagreement() {
  return (
    <p className="rounded-lg border-l-[3px] border-gold bg-gold-tint px-4 py-2.5 text-[13.5px]">
      The documents disagree on part of this. Each version is given with the document it comes from.
    </p>
  );
}

function TurnError({ message, onRetry, testId }: { message: string; onRetry: () => void; testId: string }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <ErrorNote testId={`${testId}-error`}>{message}</ErrorNote>
      <Button variant="secondary" size="sm" onClick={onRetry} data-testid={`${testId}-retry`}>
        Try again
      </Button>
    </div>
  );
}

function Answer({ turn, testId }: { turn: Turn; testId: string }) {
  const { highlighted, anchorFor, jump } = useSourceJump(turn.id);
  const titles = useMemo(
    () => Object.fromEntries([...turn.documents.map((doc) => [doc.label, doc.title]), ...turn.figures.map((f) => [f.label, f.description])]),
    [turn.documents, turn.figures],
  );
  const done = turn.stage === "done";
  const cited = citedDocuments(turn);
  return (
    <>
      {done ? <Attribution documents={cited.length} figures={turn.figures.filter((f) => f.cited).length} /> : null}
      {done && turn.text.includes(DISAGREEMENT_LEAD) ? <Disagreement /> : null}
      {turn.text ? <AnswerText markdown={turn.text} titles={titles} onCite={jump} testIdPrefix={testId} /> : null}
      {done && turn.chart ? <AnswerChart chart={turn.chart} testId={testId} /> : null}
      {done && !turn.chart && turn.chartNote ? <p className="text-[13px] text-ink-soft italic" data-testid={`${testId}-chart-note`}>{turn.chartNote}</p> : null}
      {done ? <AnswerFigures turn={turn} anchorFor={anchorFor} highlighted={highlighted} testId={testId} /> : null}
      {done && turn.documents.length ? (
        <AnswerSources cited={cited} uncited={turn.documents.filter((doc) => !doc.cited)} anchorFor={anchorFor} highlighted={highlighted} testIdPrefix={testId} />
      ) : null}
    </>
  );
}

/** One question and everything that comes back for it. */
export function AskTurn({ turn, onRetry }: { turn: Turn; onRetry: (turn: Turn) => void }) {
  const testId = `ask-${turn.id}`;
  const working = turn.stage === "searching" || turn.stage === "counting" || turn.stage === "writing";
  const noInformation = turn.stage === "done" && turn.status === "no_information";
  return (
    <section id={turn.id} aria-labelledby={`${turn.id}-question`} className="flex scroll-mt-6 flex-col gap-4" data-testid={testId}>
      <div className="flex flex-col gap-1">
        <p className="text-[12.5px] text-ink-soft">Question</p>
        <h2 id={`${turn.id}-question`} className="text-[22px] leading-snug break-words">
          {turn.question}
        </h2>
      </div>
      {working ? <AskProgress turn={turn} testId={`${testId}-progress`} /> : null}
      {noInformation ? <NoInformation testIdPrefix={testId} /> : null}
      {!noInformation && turn.stage !== "error" ? <Answer turn={turn} testId={testId} /> : null}
      {turn.stage === "done" && turn.exportView ? <ExportMenu view={turn.exportView} testId={testId} /> : null}
      {turn.stage === "error" && turn.error ? <TurnError message={turn.error} onRetry={() => onRetry(turn)} testId={testId} /> : null}
    </section>
  );
}
