import Link from "next/link";

import { Lines } from "@/components/accountability/figure-lines";

import type { PetitionFigures as Figures } from "@/lib/api/types";

/**
 * How the MCE handled residents' petitions over the same twelve months: the review, and the response owed to
 * each that reached its signatures. Exact counts: they count the MCE's decisions on public petitions, not residents.
 */
export function PetitionFigures({ figures }: { figures: Figures }) {
  const reasons = figures.refusals.filter((r) => r.count > 0);
  return (
    <article className="flex flex-col gap-4 rounded-xl border bg-card p-4 sm:p-5" data-testid="responsiveness-petitions">
      <h3 className="text-[18px]">The MCE and residents&apos; petitions</h3>
      <Lines title="Review" lines={[
        { label: "Petitions sent for review", value: figures.sent.toLocaleString(), testId: "responsiveness-petitions-sent" },
        { label: "Published by the MCE", value: figures.published_by_mce.toLocaleString(), testId: "responsiveness-petitions-published" },
        { label: "Published automatically: the MCE didn't decide within 72 hours", value: figures.published_automatically.toLocaleString(), testId: "responsiveness-petitions-automatic" },
        { label: "Refused", value: figures.refused.toLocaleString(), testId: "responsiveness-petitions-refused" },
      ]}>
        {reasons.length ? <p className="text-[12.5px] text-ink-soft">Refused for: {reasons.map((r) => `${r.label.toLowerCase()} (${r.count})`).join(", ")}.</p> : null}
      </Lines>
      <Lines title={`Response to the ${figures.reached_threshold.toLocaleString()} that reached their signatures`} lines={[
        { label: "Answered within 30 days", value: figures.answered_in_time.toLocaleString(), testId: "responsiveness-petitions-in-time" },
        { label: "Answered after the 30 days", value: figures.answered_late.toLocaleString(), testId: "responsiveness-petitions-late" },
        { label: "No response after 30 days", value: figures.unanswered.toLocaleString(), testId: "responsiveness-petitions-unanswered" },
        { label: "Still within the 30 days", value: figures.waiting.toLocaleString(), testId: "responsiveness-petitions-waiting" },
      ]} />
      <p className="text-[12.5px] text-ink-soft">
        Exact counts, unlike the report figures: they count the MCE&apos;s decisions on public petitions, not residents.{" "}
        <Link href="/petitions" className="text-teal underline-offset-2 hover:underline" data-testid="responsiveness-petitions-link">See the petitions</Link>
      </p>
    </article>
  );
}
