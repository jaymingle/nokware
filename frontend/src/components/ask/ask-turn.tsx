"use client";

import { LanguagesIcon } from "lucide-react";
import { useMemo, useState } from "react";

import { AnswerChart } from "@/components/ask/answer-chart";
import { AnswerSources } from "@/components/ask/answer-sources";
import { AnswerText } from "@/components/ask/answer-text";
import { AskProgress } from "@/components/ask/ask-progress";
import { FigureCard } from "@/components/ask/figure-card";
import { MoreMenu } from "@/components/ask/more-menu";
import { NoInformation } from "@/components/ask/no-information";
import { ErrorNote } from "@/components/documents/panels";
import { ReadAloud } from "@/components/read-aloud/read-aloud";
import { Button } from "@/components/ui/button";
import { useAskSourceJump, type AskSourceJump } from "@/hooks/use-ask-source-jump";
import { answerAudio } from "@/lib/api/public";
import { DISAGREEMENT_LEAD } from "@/lib/ask/sources";
import { attribution, citedDocuments, type Turn } from "@/lib/ask/turn";
import { cn } from "@/lib/utils";

import type { ExportView } from "@/lib/api/types";

/** A heading, so a screen reader can move from question to question. */
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
    <p className="rounded-lg border-s-[3px] border-gold bg-gold-tint px-4 py-2.5 text-[14px]">
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

function TranslationNote({ showing, onToggle, testId }: { showing: "asked" | "english"; onToggle: () => void; testId: string }) {
  return (
    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px] text-ink-soft" data-testid={`${testId}-translation`}>
      <LanguagesIcon aria-hidden className="size-3.5" />
      Translated by machine from the English answer, which the sources are in.
      <button type="button" onClick={onToggle} className="cursor-pointer text-teal underline underline-offset-2"
        data-testid={`${testId}-show-english`}>
        {showing === "asked" ? "Show the English" : "Show the translation"}
      </button>
    </p>
  );
}

/** Why there is no chart, told before the answer: a request that produces silence tells the reader neither
    that it failed nor that it was never tried. */
function ChartNote({ note, testId }: { note: string; testId: string }) {
  return (
    <p className="text-[13.5px] text-ink-soft italic" data-testid={`${testId}-chart-note`}>{note}</p>
  );
}

function AnsweredBody({ turn, shown, jump, testId }: { turn: Turn; shown: string; jump: AskSourceJump; testId: string }) {
  const titles = useMemo(
    () => Object.fromEntries([...turn.documents.map((doc) => [doc.label, doc.title]), ...turn.figures.map((f) => [f.label, f.description])]),
    [turn.documents, turn.figures],
  );
  const done = turn.stage === "done";
  return (
    <>
      {shown ? (
        <AnswerText markdown={shown} titles={titles} onCite={jump.jump} testIdPrefix={testId}
          repeatedBelow={done && turn.figures.some((figure) => figure.cited && figure.rows.length > 0)} />
      ) : null}
      {turn.stage === "writing" && turn.text ? <p className="text-[12.5px] text-ink-soft" role="status">Writing…</p> : null}
      {/* Checked against the English: a translation would not contain the lead wording. */}
      {done && turn.english.includes(DISAGREEMENT_LEAD) ? <Disagreement /> : null}
    </>
  );
}

function ReplyBody({ turn, shown, jump, onRetry, testId }: { turn: Turn; shown: string; jump: AskSourceJump; onRetry: () => void; testId: string }) {
  const done = turn.stage === "done";
  const working = turn.stage === "searching" || turn.stage === "counting" || turn.stage === "translating"
    || (turn.stage === "writing" && !turn.text);
  if (turn.stage === "error") return <TurnError message={turn.error ?? ""} onRetry={onRetry} testId={testId} />;
  return (
    <>
      {working ? <AskProgress turn={turn} testId={`${testId}-progress`} /> : null}
      {done && !turn.chart && turn.chartNote ? <ChartNote note={turn.chartNote} testId={testId} /> : null}
      {done && turn.status === "no_information"
        ? <NoInformation testIdPrefix={testId} />
        : <AnsweredBody turn={turn} shown={shown} jump={jump} testId={testId} />}
    </>
  );
}

/**
 * Beside the answer, not under everything else: an answer with a chart and dozens of figures runs thousands of
 * pixels. Listening is how some people read at all, so it stays a button; the rest folds into More.
 */
function ReplyActions({ turn, view, answer, testId }: { turn: Turn; view: ExportView; answer: string; testId: string }) {
  return (
    <div className="flex flex-wrap items-start gap-x-3 gap-y-2">
      {turn.speakable ? <ReadAloud load={(part) => answerAudio(view, part)} label="Listen to this answer" testId={`${testId}-listen`} /> : null}
      <MoreMenu view={view} answer={answer} testId={testId} />
      {!turn.speakable && turn.speechNote
        ? <p className="basis-full text-[12.5px] text-ink-soft" data-testid={`${testId}-speech-note`}>{turn.speechNote}</p>
        : null}
    </div>
  );
}

/** Below the answer and quieter: the chart the question asked for, then the figures, then where it all came from. */
function BelowAnswer({ turn, jump, testId }: { turn: Turn; jump: AskSourceJump; testId: string }) {
  const figures = turn.figures.filter((figure) => figure.cited);
  const said = attribution(turn);
  if (!turn.chart && !figures.length && !turn.documents.length) return null;
  return (
    <div className="flex flex-col gap-4 border-t bg-paper-subtle px-4 py-4 sm:px-5" data-testid={`${testId}-attachments`}>
      {turn.chart ? <AnswerChart chart={turn.chart} testId={testId} /> : null}
      {figures.length ? (
        <section aria-label="Figures" className="flex flex-col gap-2.5">
          <h3 className="font-sans text-[12px] font-medium tracking-wide text-ink-soft uppercase">Figures</h3>
          {figures.map((figure) => (
            <FigureCard key={figure.label} figure={figure} anchorId={jump.anchorFor(figure.label)} highlighted={jump.highlighted === figure.label} testIdPrefix={testId} />
          ))}
        </section>
      ) : null}
      {said ? <p className="text-[12.5px] text-ink-soft" data-testid={`${testId}-attribution`}>{said}</p> : null}
      {turn.documents.length ? (
        <AnswerSources cited={citedDocuments(turn)} uncited={turn.documents.filter((doc) => !doc.cited)}
          open={jump.sourcesOpen} onOpenChange={jump.setSourcesOpen} anchorFor={jump.anchorFor}
          highlighted={jump.highlighted} testIdPrefix={testId} />
      ) : null}
    </div>
  );
}

function ReplyMessage({ turn, anchorPrefix, onRetry, testId }: { turn: Turn; anchorPrefix: string; onRetry: () => void; testId: string }) {
  const jump = useAskSourceJump(anchorPrefix);
  const [showing, setShowing] = useState<"asked" | "english">("asked");
  const done = turn.stage === "done";
  const shown = showing === "english" ? turn.english : turn.text;
  return (
    <div className={cn("overflow-hidden rounded-xl border bg-card", turn.stage === "error" && "border-brick/30")}>
      <div className="flex flex-col gap-4 px-4 py-4 sm:px-5 sm:py-5">
        <ReplyBody turn={turn} shown={shown} jump={jump} onRetry={onRetry} testId={testId} />
        {done && turn.exportView ? <ReplyActions turn={turn} view={turn.exportView} answer={shown} testId={testId} /> : null}
        {done && turn.translated ? (
          <TranslationNote showing={showing} onToggle={() => setShowing(showing === "asked" ? "english" : "asked")} testId={testId} />
        ) : null}
      </div>
      {done && turn.status === "answered" ? <BelowAnswer turn={turn} jump={jump} testId={testId} /> : null}
    </div>
  );
}

export function AskTurn({ turn, scope, onRetry }: { turn: Turn; scope: string; onRetry: (turn: Turn) => void }) {
  const testId = `ask-${turn.id}`;
  const domId = `${scope}-${turn.id}`;
  return (
    <section id={domId} aria-labelledby={`${domId}-question`} className="flex scroll-mt-4 flex-col gap-3" data-testid={testId}>
      <QuestionMessage turn={turn} headingId={`${domId}-question`} testId={testId} />
      <ReplyMessage turn={turn} anchorPrefix={domId} onRetry={() => onRetry(turn)} testId={testId} />
    </section>
  );
}
