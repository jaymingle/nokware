import { ActivityIcon, LandmarkIcon } from "lucide-react";
import Link from "next/link";

import { LedgerPdfLink } from "@/components/ask/ledger-pdf-link";
import { countedAt, labelNumber } from "@/lib/ask/figures";
import { cn } from "@/lib/utils";

import type { AskFigure } from "@/lib/api/types";

function Breakdown({ figure }: { figure: AskFigure }) {
  return (
    <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 border-t pt-2 text-[13.5px]">
      {figure.rows.map((row) => (
        <div key={row.name} className="contents">
          <dt>{row.name}</dt>
          <dd className="text-end text-ink-soft tabular-nums">{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

type FigureCardProps = { figure: AskFigure; anchorId: string; highlighted: boolean; testIdPrefix: string };

/** Where a budget figure comes from: the document, the year, and how much of it the rows cover. */
function ReadFromDocument({ figure, testId }: { figure: AskFigure; testId: string }) {
  return (
    <div className="flex flex-col gap-1.5 text-[12px] text-ink-soft">
      <p>
        Read from {figure.document_title}
        {figure.year ? ` (${figure.year})` : ""}. Approved amounts, not money released or spent.
        {figure.coverage ? ` These rows are ${figure.coverage} of what that document states it details.` : ""}
      </p>
      {figure.document_id ? <LedgerPdfLink documentId={figure.document_id} testId={`${testId}-pdf`} /> : null}
    </div>
  );
}

/** A figure cited beside the documents: a live count of reports, or an approved amount read from a budget. */
export function FigureCard({ figure, anchorId, highlighted, testIdPrefix }: FigureCardProps) {
  const fromDocument = figure.source === "documents";
  return (
    <article
      id={anchorId}
      tabIndex={-1}
      data-testid={`${testIdPrefix}-figure-${figure.label}`}
      data-highlighted={highlighted || undefined}
      className={cn(
        "flex scroll-mt-6 gap-3 rounded-lg border border-gold/40 bg-paper-warm p-3.5 transition-[box-shadow,border-color] duration-300 outline-none",
        highlighted && "border-gold ring-2 ring-gold/40",
      )}
    >
      <span aria-hidden className="grid h-6 min-w-6 shrink-0 place-items-center rounded-md bg-gold-tint px-1.5 text-[12px] font-medium text-ink tabular-nums">
        {figure.label.replace(/\d+$/, "")}{labelNumber(figure.label)}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <p className="flex items-center gap-1.5 text-[12px] font-medium tracking-wide text-ink uppercase">
          {fromDocument ? <LandmarkIcon aria-hidden className="size-3.5 text-gold" /> : <ActivityIcon aria-hidden className="size-3.5 text-gold" />}
          {fromDocument ? "Approved budget" : "Live report data"}
          <span className="sr-only">, figure {labelNumber(figure.label)}</span>
        </p>
        <h3 className="text-[15px] leading-snug">{figure.description}</h3>
        <p className="font-heading text-[24px] leading-none tabular-nums">{figure.value}</p>
        {figure.rows.length ? <Breakdown figure={figure} /> : null}
        {fromDocument ? (
          <ReadFromDocument figure={figure} testId={`${testIdPrefix}-figure-${figure.label}`} />
        ) : (
          <p className="text-[12px] text-ink-soft">
            {countedAt(figure.counted_at ?? "")} from reports residents filed with Nokware, not a published document. Reports about
            someone&apos;s safety are never counted, and counts from 1 to 4 read &ldquo;fewer than 5&rdquo;.{" "}
            <Link href="/dashboard" className="text-teal underline underline-offset-2" data-testid={`${testIdPrefix}-figure-${figure.label}-dashboard`}>
              See the dashboard
            </Link>
          </p>
        )}
      </div>
    </article>
  );
}
