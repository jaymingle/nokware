import { LedgerPdfLink } from "@/components/ask/ledger-pdf-link";

import type { ReportingGap } from "@/lib/api/types";

function Gap({ gap }: { gap: ReportingGap }) {
  const testId = `gap-${gap.id}`;
  return (
    <article className="flex flex-col gap-2.5 rounded-xl border border-gold/40 bg-paper-warm p-4 sm:p-5" data-testid={testId}>
      <div>
        <h3 className="text-[18px] leading-snug" data-testid={`${testId}-headline`}>
          Accra&apos;s most recent published {gap.subject.toLowerCase()} figures are {gap.years_since} years old
        </h3>
        <p className="mt-1 text-[13.5px] text-ink-soft">
          The newest figures The Ledger holds are for {gap.latest_year}: {gap.figures}. Nothing published since gives
          them again.
        </p>
      </div>
      <blockquote className="border-s-2 border-gold ps-3 text-[13.5px] leading-relaxed text-ink-soft">
        &ldquo;{gap.quote}&rdquo;
      </blockquote>
      <p className="text-[12.5px] text-ink-soft">{gap.why}</p>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t pt-2.5">
        <LedgerPdfLink documentId={gap.document_id} testId={`${testId}-pdf`} />
        <p className="text-[12px] text-ink-soft">
          {gap.document_title}. The Ledger was searched for {gap.searched.map((word) => `“${word}”`).join(", ")} on{" "}
          {new Date(gap.checked).toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" })}.
        </p>
      </div>
    </article>
  );
}

/** Figures the Assembly's documents once reported and haven't since: the gap the record itself can't show. */
export function ReportingGaps({ gaps, about }: { gaps?: ReportingGap[]; about?: string }) {
  // Optional on purpose: an API that predates these findings must not blank the record.
  if (!gaps?.length || !about) return null;
  return (
    <section aria-labelledby="reporting-gaps" className="flex flex-col gap-3" data-testid="reporting-gaps">
      <div>
        <h2 id="reporting-gaps" className="text-[22px] leading-snug">
          Figures that stop
        </h2>
        <p className="mt-1 max-w-[70ch] text-[14px] text-ink-soft">{about}</p>
      </div>
      {gaps.map((gap) => (
        <Gap key={gap.id} gap={gap} />
      ))}
    </section>
  );
}
