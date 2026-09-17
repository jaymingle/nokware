import { FileTextIcon, ScaleIcon } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { ASSUMPTION_NOTE, LEDGER_YEAR_NOTE, STATE_LABELS, dateLabel, gapSentence, rtiHref } from "@/lib/accountability";
import { ledgerFileUrl } from "@/lib/api/public";

import type { RecordDocument, RecordPeriod, RecordRequirement } from "@/lib/api/types";

function Documents({ documents, testId }: { documents: RecordDocument[]; testId: string }) {
  return (
    <ul className="flex flex-col gap-1.5" data-testid={testId}>
      {documents.map((doc) => (
        <li key={doc.id} className="flex flex-wrap items-baseline gap-x-2 text-[14px]">
          <a href={ledgerFileUrl(doc.id)} target="_blank" rel="noopener" className="inline-flex items-center gap-1 text-teal underline underline-offset-2">
            <FileTextIcon aria-hidden className="size-3.5 shrink-0" />
            {doc.title}
          </a>
          <span className="text-[12.5px] text-ink-soft">
            {[doc.department_name, doc.year].filter(Boolean).join(" · ")}
            {doc.year_source === "ledger" ? <sup title={LEDGER_YEAR_NOTE}> †</sup> : null}
          </span>
          {doc.note ? <span className="basis-full text-[12.5px] text-ink-soft" data-testid={`${testId}-note`}>{doc.note}</span> : null}
        </li>
      ))}
    </ul>
  );
}

/** What the Ledger does hold that year from the same departments or categories: a gap means more beside it. */
function Nearby({ requirement, period, testId }: { requirement: RecordRequirement; period: RecordPeriod; testId: string }) {
  const more = period.nearby_total - period.nearby.length;
  return (
    <div className="flex flex-col gap-2 rounded-lg bg-paper-subtle px-3.5 py-3">
      <p className="text-[13px] font-medium">
        {period.nearby_total === 0
          ? `The Ledger holds nothing from ${requirement.nearby_scope} for ${period.year}.`
          : `What The Ledger does hold from ${requirement.nearby_scope} for ${period.year}: ${period.nearby_total} document${period.nearby_total === 1 ? "" : "s"}`}
      </p>
      {period.nearby.length ? <Documents documents={period.nearby} testId={`${testId}-nearby`} /> : null}
      {more > 0 ? <p className="text-[12.5px] text-ink-soft">and {more} more</p> : null}
    </div>
  );
}

function Missing({ requirement, period, checked, testId }: { requirement: RecordRequirement; period: RecordPeriod; checked: string; testId: string }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-[14.5px]" data-testid={`${testId}-gap`}>{gapSentence(checked)}</p>
      <p className="text-[13px] text-ink-soft">
        That doesn&apos;t mean it doesn&apos;t exist: it may simply not have been published online.
        {period.expected_from ? ` We count it as expected from ${dateLabel(period.expected_from)} (${requirement.expected_note?.toLowerCase()}), by our own assumption.` : ""}
      </p>
      <Button variant="secondary" size="sm" className="w-fit" asChild>
        <Link href={rtiHref(requirement, period)} data-testid={`${testId}-request`}>
          <ScaleIcon data-icon="inline-start" />
          Request it under the RTI Act
        </Link>
      </Button>
    </div>
  );
}

function Explanation({ requirement, period, checked, testId }: { requirement: RecordRequirement; period: RecordPeriod; checked: string; testId: string }) {
  if (period.state === "held") {
    return (
      <div className="flex flex-col gap-3">
        <Documents documents={period.documents} testId={`${testId}-held`} />
        {period.related.length ? (
          <div className="flex flex-col gap-1.5">
            <p className="text-[13px] text-ink-soft">Also in The Ledger, related but not counted as the {requirement.name} itself:</p>
            <Documents documents={period.related} testId={`${testId}-related`} />
          </div>
        ) : null}
      </div>
    );
  }
  if (period.state === "not_due") {
    return (
      <p className="text-[14px]">
        Not yet expected. {requirement.expected_note}: from {period.expected_from ? dateLabel(period.expected_from) : "a later date"}.
        <span className="block text-[12.5px] text-ink-soft">{ASSUMPTION_NOTE}</span>
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-3">
      {period.state === "related" ? (
        <div className="flex flex-col gap-1.5">
          <p className="text-[14.5px]">The Ledger holds related documents, but not the {requirement.name} itself:</p>
          <Documents documents={period.related} testId={`${testId}-related`} />
        </div>
      ) : null}
      <Missing requirement={requirement} period={period} checked={checked} testId={testId} />
    </div>
  );
}

/** One cell of the record, opened: what is held, what isn't, and what to do about it. */
export function RecordDetail({ requirement, period, checked }: { requirement: RecordRequirement; period: RecordPeriod; checked: string }) {
  const testId = `record-${requirement.id}-${period.label.replace(/\W+/g, "-")}`;
  return (
    <section aria-live="polite" className="flex flex-col gap-3 rounded-xl border bg-card p-4 sm:p-5" data-testid={`${testId}-detail`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-[18px]">{requirement.name}, {period.label}</h3>
        <span className="text-[12.5px] text-ink-soft">{STATE_LABELS[period.state]}</span>
      </div>
      {requirement.issued_by ? <p className="text-[13px] text-ink-soft">Issued by {requirement.issued_by}, not by the Assembly.</p> : null}
      <Explanation requirement={requirement} period={period} checked={checked} testId={testId} />
      {period.state !== "held" ? <Nearby requirement={requirement} period={period} testId={testId} /> : null}
      {[...period.documents, ...period.related, ...period.nearby].some((doc) => doc.year_source === "ledger") ? (
        <p className="text-[12px] text-ink-soft" data-testid={`${testId}-ledger-year`}>† {LEDGER_YEAR_NOTE}</p>
      ) : null}
      {requirement.undated.length ? (
        <div className="flex flex-col gap-1.5">
          <p className="text-[13px] text-ink-soft">Also in The Ledger, with no year stated:</p>
          <Documents documents={requirement.undated} testId={`${testId}-undated`} />
        </div>
      ) : null}
    </section>
  );
}
