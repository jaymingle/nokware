import Link from "next/link";

import { formatDate } from "@/lib/time";

import type { UnpublishedData } from "@/lib/api/types";

/** Where to ask the Assembly for it, with the wording already filled in. */
function rtiHref(finding: UnpublishedData): string {
  return `/rti?${new URLSearchParams({ document: finding.rti_document, period: finding.rti_period })}`;
}

function Finding({ finding }: { finding: UnpublishedData }) {
  const testId = `unpublished-${finding.id}`;
  // Not the warm gold of "Figures that stop": that is a figure that has aged,
  // this is an absence, and the record already marks an absence in brick. Side
  // by side, the two read as one undifferentiated block of warm boxes.
  return (
    <article className="flex flex-col gap-2.5 rounded-xl border border-s-[3px] border-brick/25 border-s-brick bg-card p-4 sm:p-5" data-testid={testId}>
      <div>
        {/* The finding's own sentence, as written: nothing here is composed out of a label. */}
        <h3 className="text-[18px] leading-snug" data-testid={`${testId}-headline`}>{finding.headline}</h3>
        <p className="mt-1 text-[13.5px] text-ink-soft">{finding.matters}</p>
      </div>
      <div className="flex flex-col gap-1.5 rounded-lg bg-paper-subtle px-3.5 py-3">
        <h4 className="text-[12px] font-medium tracking-wide text-ink-soft uppercase">Where we looked</h4>
        <dl className="flex flex-col gap-1.5 text-[13px]">
          {finding.checked.map((source) => (
            <div key={source.url} className="flex flex-col sm:flex-row sm:gap-3">
              <dt className="sm:w-[13rem] sm:shrink-0">
                <a href={source.url} target="_blank" rel="noopener"
                  className="text-teal underline underline-offset-2" data-testid={`${testId}-source-${source.name.replace(/\W+/g, "-").toLowerCase()}`}>
                  {source.name}
                </a>
              </dt>
              <dd className="text-ink-soft">{source.holds}</dd>
            </div>
          ))}
        </dl>
      </div>
      <p className="text-[12.5px] text-ink-soft">{finding.instead} Checked {formatDate(finding.checked_on)}.</p>
      <div className="border-t pt-2.5">
        <Link href={rtiHref(finding)} className="text-[13px] text-teal underline underline-offset-2" data-testid={`${testId}-rti`}>
          Request it from the Assembly under the RTI Act
        </Link>
      </div>
    </article>
  );
}

/**
 * Things the public record would need that nobody publishes at all.
 *
 * The publishing record asks whether a document exists; "Figures that stop" asks
 * whether a figure is still being given. This asks whether the thing was ever
 * published by anyone — the question Accra's electoral-area boundaries failed,
 * which is why the dashboard draws those areas as tiles and not as shapes.
 */
export function UnpublishedRecord({ findings, about }: { findings?: UnpublishedData[]; about?: string }) {
  // Optional on purpose, like the reporting gaps: an API that predates these findings must not blank the record.
  const written = findings?.filter((finding) => finding.headline) ?? [];
  if (!written.length || !about) return null;
  return (
    <section aria-labelledby="unpublished-data" className="flex flex-col gap-3" data-testid="unpublished-data">
      <div>
        <h2 id="unpublished-data" className="text-[22px] leading-snug">Never published at all</h2>
        <p className="mt-1 max-w-[70ch] text-[14px] text-ink-soft">{about}</p>
      </div>
      {written.map((finding) => (
        <Finding key={finding.id} finding={finding} />
      ))}
    </section>
  );
}
