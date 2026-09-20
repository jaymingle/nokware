import { StatusMark } from "@/components/status-tag";
import { timelineText } from "@/lib/petitions";
import { petitionEventTone } from "@/lib/status";
import { formatDate } from "@/lib/time";

import type { PetitionTimelineEntry } from "@/lib/api/types";

/** What happened to a petition and when, in the same words for the public page and for the person who started it. */
export function PetitionTimeline({ entries, testId }: { entries: PetitionTimelineEntry[]; testId?: string }) {
  return (
    <ol className="flex flex-col gap-2 text-[13.5px]" data-testid={testId}>
      {entries.map((entry) => (
        <li key={`${entry.action}-${entry.at}`} className="flex flex-wrap items-baseline gap-x-3">
          <span className="flex w-28 shrink-0 items-center gap-2 text-ink-soft tabular-nums">
            <StatusMark tone={petitionEventTone(entry.action)} className="size-3.5" />
            {formatDate(entry.at)}
          </span>
          <span>{timelineText(entry)}</span>
        </li>
      ))}
    </ol>
  );
}
