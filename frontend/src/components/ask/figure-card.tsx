import Link from "next/link";
import { ActivityIcon } from "lucide-react";

import { countedAt, labelNumber } from "@/lib/ask/figures";
import { cn } from "@/lib/utils";

import type { AskFigure } from "@/lib/api/types";

function Breakdown({ figure }: { figure: AskFigure }) {
  return (
    <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 border-t pt-2 text-[13.5px]">
      {figure.rows.map((row) => (
        <div key={row.name} className="contents">
          <dt>{row.name}</dt>
          <dd className="text-right text-ink-soft tabular-nums">{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

type FigureCardProps = { figure: AskFigure; anchorId: string; highlighted: boolean; testIdPrefix: string };

/** A live count of reports, cited like a source but plainly not a document: what was counted, the result, and when. */
export function FigureCard({ figure, anchorId, highlighted, testIdPrefix }: FigureCardProps) {
  return (
    <article
      id={anchorId}
      tabIndex={-1}
      data-testid={`${testIdPrefix}-figure-${figure.label}`}
      data-highlighted={highlighted || undefined}
      className={cn(
        "flex scroll-mt-6 gap-3 rounded-xl border border-gold/40 bg-paper-warm p-4 transition-[box-shadow,border-color] duration-300 outline-none sm:p-5",
        highlighted && "border-gold ring-2 ring-gold/40",
      )}
    >
      <span aria-hidden className="grid h-6 min-w-6 shrink-0 place-items-center rounded-md bg-gold-tint px-1.5 text-[12px] font-medium text-ink tabular-nums">
        R{labelNumber(figure.label)}
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <p className="flex items-center gap-1.5 text-[12px] font-medium tracking-wide text-ink uppercase">
          <ActivityIcon aria-hidden className="size-3.5 text-gold" />
          Live report data <span className="sr-only">, figure {labelNumber(figure.label)}</span>
        </p>
        <h3 className="text-[15px] leading-snug">{figure.description}</h3>
        <p className="font-heading text-[26px] leading-none tabular-nums">{figure.value}</p>
        {figure.rows.length ? <Breakdown figure={figure} /> : null}
        <p className="text-[12px] text-ink-soft">
          {countedAt(figure.counted_at)} from reports residents filed with Nokware, not a published document. Reports about
          someone&apos;s safety are never counted, and counts from 1 to 4 read &ldquo;fewer than 5&rdquo;.{" "}
          <Link href="/dashboard" className="text-teal underline-offset-2 hover:underline" data-testid={`${testIdPrefix}-figure-${figure.label}-dashboard`}>
            See the dashboard
          </Link>
        </p>
      </div>
    </article>
  );
}
