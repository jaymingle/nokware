"use client";

import { LanguagesIcon } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AnswerChart } from "@/components/ask/answer-chart";
import { AnswerSources } from "@/components/ask/answer-sources";
import { AnswerText } from "@/components/ask/answer-text";
import { AskProgress } from "@/components/ask/ask-progress";
import { ExportMenu } from "@/components/ask/export-menu";
import { FigureCard } from "@/components/ask/figure-card";
import { NoInformation } from "@/components/ask/no-information";
import { ErrorNote } from "@/components/documents/panels";
import { ReadAloud } from "@/components/read-aloud/read-aloud";
import { Button } from "@/components/ui/button";
import { answerAudio } from "@/lib/api/public";
import { DISAGREEMENT_LEAD } from "@/lib/ask/sources";
import { attribution, citedDocuments, type Turn } from "@/lib/ask/turn";
import { cn } from "@/lib/utils";

import type { ExportView } from "@/lib/api/types";

const HIGHLIGHT_MS = 2400;

/** Jumping from a citation to its source: scroll, focus, and briefly highlight the card. */
function useSourceJump(anchorPrefix: string) {
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  const anchorFor = useCallback((label: string) => `${anchorPrefix}-${label}`, [anchorPrefix]);
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

type Jump = ReturnType<typeof useSourceJump>;

/** The person's question, on the right. A heading, so a screen reader can move from question to question. */
function QuestionMessage({ turn, headingId, testId }: { turn: Turn; headingId: string; testId: string }) {
  return (
    <div className="flex justify-end ps-10 sm:ps-16">
      <h2 id={headingId} className="max-w-full rounded-2xl rounded-ee-md border border-teal/20 bg-teal-tint px-4 py-2.5 font-sans text-[15.5px] leading-snug break-words text-ink"
        data-testid={`${testId}-question`}>
        <span className="sr-only">You asked: </span>
        {turn.question}
      </h2>
    </div>
  );
}

function Disagreement() {
  return (
    <p className="rounded-lg border-s-[3px] border-gold bg-gold-tint px-4 py-2.5 text-[13.5px]">
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

/** A machine translated this answer: say so, and offer the English it was checked in. */
function TranslationNote({ showing, onToggle, testId }: { showing: "asked" | "english"; onToggle: () => void; testId: string }) {
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 border-t pt-2.5 text-[12.5px] text-ink-soft" data-testid={`${testId}-translation`}>
      <LanguagesIcon aria-hidden className="size-3.5" />
      Translated by machine from the English answer, which the sources are in.
      <button type="button" onClick={onToggle} className="cursor-pointer text-teal underline underline-offset-2"
        data-testid={`${testId}-show-english`}>
        {showing === "asked" ? "Show the English" : "Show the translation"}
      </button>
    </p>
  );
}

/** The words of the reply: progress while it works, then the answer (or why there isn't one). */
function ReplyBody({ turn, jump, onRetry, testId }: { turn: Turn; jump: Jump; onRetry: () => void; testId: string }) {
  const [showing, setShowing] = useState<"asked" | "english">("asked");
  const titles = useMemo(
    () => Object.fromEntries([...turn.documents.map((doc) => [doc.label, doc.title]), ...turn.figures.map((f) => [f.label, f.description])]),
    [turn.documents, turn.figures],
  );
  const done = turn.stage === "done";
  const working = turn.stage === "searching" || turn.stage === "counting" || turn.stage === "translating"
    || (turn.stage === "writing" && !turn.text);
  const shown = showing === "english" ? turn.english : turn.text;
  if (turn.stage === "error") return <TurnError message={turn.error ?? ""} onRetry={onRetry} testId={testId} />;
  if (done && turn.status === "no_information") return <NoInformation testIdPrefix={testId} />;
  return (
    <>
      {working ? <AskProgress turn={turn} testId={`${testId}-progress`} /> : null}
      {/* The disagreement note reads the English: the wording it looks for is the answer as it was checked. */}
      {done && turn.english.includes(DISAGREEMENT_LEAD) ? <Disagreement /> : null}
      {shown ? (
        <AnswerText markdown={shown} titles={titles} onCite={jump.jump} testIdPrefix={testId}
          repeatedBelow={done && turn.figures.some((figure) => figure.cited && figure.rows.length > 0)} />
      ) : null}
      {turn.stage === "writing" && turn.text ? <p className="text-[12.5px] text-ink-soft" role="status">Writing…</p> : null}
      {done && turn.translated ? (
        <TranslationNote showing={showing} onToggle={() => setShowing(showing === "asked" ? "english" : "asked")} testId={testId} />
      ) : null}
    </>
  );
}

/** What the answer rests on, attached to it: the chart, the live figures, then the documents. */
function Attachments({ turn, jump, testId }: { turn: Turn; jump: Jump; testId: string }) {
  const figures = turn.figures.filter((figure) => figure.cited);
  const cited = citedDocuments(turn);
  const uncited = turn.documents.filter((doc) => !doc.cited);
  const note = !turn.chart && turn.chartNote;
  if (!turn.chart && !note && !figures.length && !turn.documents.length) return null;
  return (
    <div className="flex flex-col gap-4 border-t bg-paper-subtle px-4 py-4 sm:px-5" data-testid={`${testId}-attachments`}>
      {turn.chart ? <AnswerChart chart={turn.chart} testId={testId} /> : null}
      {note ? <p className="text-[13px] text-ink-soft italic" data-testid={`${testId}-chart-note`}>{turn.chartNote}</p> : null}
      {figures.length ? (
        <section aria-label="Figures" className="flex flex-col gap-2.5">
          <h3 className="font-sans text-[12px] font-medium tracking-wide text-ink-soft uppercase">Figures</h3>
          {figures.map((figure) => (
            <FigureCard key={figure.label} figure={figure} anchorId={jump.anchorFor(figure.label)} highlighted={jump.highlighted === figure.label} testIdPrefix={testId} />
          ))}
        </section>
      ) : null}
      {turn.documents.length ? <AnswerSources cited={cited} uncited={uncited} anchorFor={jump.anchorFor} highlighted={jump.highlighted} testIdPrefix={testId} /> : null}
    </div>
  );
}

/**
 * What can be done with a finished answer: hear it read aloud (unless it touches
 * on someone's safety), or download it. At the head of the reply, because an
 * answer with a chart and forty-two figures runs thousands of pixels and nobody
 * scrolls past all of it to find out they could have downloaded it.
 */
function ReplyTools({ turn, view, testId }: { turn: Turn; view: ExportView; testId: string }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b bg-paper-subtle px-4 py-2 sm:px-5">
      {turn.speakable ? <ReadAloud load={(part) => answerAudio(view, part)} label="Listen to this answer" testId={`${testId}-listen`} /> : <span />}
      <ExportMenu view={view} testId={testId} />
    </div>
  );
}

/** Nokware's reply, on the left under its mark: the answer, with what it rests on and what can be done with it. */
function ReplyMessage({ turn, anchorPrefix, onRetry, testId }: { turn: Turn; anchorPrefix: string; onRetry: () => void; testId: string }) {
  const jump = useSourceJump(anchorPrefix);
  const done = turn.stage === "done";
  const answered = done && turn.status === "answered";
  const said = done ? attribution(turn) : null;
  return (
    <div className="flex flex-col gap-2">
      <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]">
        <span aria-hidden className="grid size-7 place-items-center rounded-lg bg-ink font-heading text-[15px] leading-none text-paper">N</span>
        <span className="font-medium text-ink">Nokware</span>
        {said ? <span className="flex items-center gap-1.5 text-ink-soft" data-testid={`${testId}-attribution`}><span aria-hidden className="size-1.5 rounded-full bg-teal" />{said}</span> : null}
      </p>
      <div className={cn("overflow-hidden rounded-xl rounded-ss-md border bg-card sm:ms-9", turn.stage === "error" && "border-brick/30")}>
        {done && turn.exportView ? <ReplyTools turn={turn} view={turn.exportView} testId={testId} /> : null}
        <div className="flex flex-col gap-3.5 px-4 py-4 sm:px-5">
          <ReplyBody turn={turn} jump={jump} onRetry={onRetry} testId={testId} />
        </div>
        {answered ? <Attachments turn={turn} jump={jump} testId={testId} /> : null}
      </div>
    </div>
  );
}

/** One exchange in the conversation: the question as the person's message, the answer as Nokware's. */
export function AskTurn({ turn, scope, onRetry }: { turn: Turn; scope: string; onRetry: (turn: Turn) => void }) {
  const testId = `ask-${turn.id}`;
  const domId = `${scope}-${turn.id}`;
  return (
    <section id={domId} aria-labelledby={`${domId}-question`} className="flex scroll-mt-4 flex-col gap-4" data-testid={testId}>
      <QuestionMessage turn={turn} headingId={`${domId}-question`} testId={testId} />
      <ReplyMessage turn={turn} anchorPrefix={domId} onRetry={() => onRetry(turn)} testId={testId} />
    </section>
  );
}
