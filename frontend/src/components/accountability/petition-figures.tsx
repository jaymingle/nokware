import Link from "next/link";

import { Lines } from "@/components/accountability/figure-lines";
import { lowerFirst } from "@/lib/text";

import type { PetitionFigures as Figures } from "@/lib/api/types";

export function PetitionFigures({ figures }: { figures: Figures }) {
  const grounds = figures.removals.filter((r) => r.count > 0);
  return (
    <article className="flex flex-col gap-4 rounded-xl border bg-card p-4 sm:p-5" data-testid="responsiveness-petitions">
      <h2 className="text-[18px]">The MCE and residents&apos; petitions</h2>
      {/* Publishing and removing are residents' and contributors' doing, not the MCE's: only the answering below
          is a figure the MCE can be held to. */}
      <Lines title="What happened to petitions" lines={[
        { label: "Published", value: figures.published.toLocaleString(), testId: "responsiveness-petitions-published" },
        { label: "Mended and published again", value: figures.republished.toLocaleString(), testId: "responsiveness-petitions-republished" },
        { label: "Removed by a contributor", value: figures.removed.toLocaleString(), testId: "responsiveness-petitions-removed" },
        ...(figures.refused_under_the_earlier_process
          ? [{ label: "Refused under the earlier review process", value: figures.refused_under_the_earlier_process.toLocaleString(), testId: "responsiveness-petitions-refused-before" }]
          : []),
      ]}>
        {grounds.length ? <p className="text-[12.5px] text-ink-soft">Removed for: {grounds.map((r) => `${lowerFirst(r.label)} (${r.count})`).join(", ")}.</p> : null}
      </Lines>
      <Lines title={`Response to the ${figures.reached_threshold.toLocaleString()} that reached their signatures`} lines={[
        { label: "Answered within 30 days", value: figures.answered_in_time.toLocaleString(), testId: "responsiveness-petitions-in-time" },
        { label: "Answered after the 30 days", value: figures.answered_late.toLocaleString(), testId: "responsiveness-petitions-late" },
        { label: "No response after 30 days", value: figures.unanswered.toLocaleString(), testId: "responsiveness-petitions-unanswered" },
        { label: "Still within the 30 days", value: figures.waiting.toLocaleString(), testId: "responsiveness-petitions-waiting" },
      ]} />
      <p className="text-[12.5px] text-ink-soft">
        Exact counts, unlike the report figures: they count public petitions, not residents.{" "}
        <Link href="/petitions" className="text-teal underline underline-offset-2" data-testid="responsiveness-petitions-link">See the petitions</Link>
      </p>
    </article>
  );
}
