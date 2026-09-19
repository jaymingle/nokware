import { formatDateTime, machineTime } from "@/lib/time";

import type { ReportTimelineEvent } from "@/lib/api/types";

/** One step of the case as the page renders it: when it happened, what happened, and the note if there is one. */
export type TimelineStep = {
  key: string;
  /** The step the server named: what gives the mark beside it its tone. */
  action: string;
  at: string;
  when: string;
  description: string;
  note: string | null;
  photos: string[];  // only an escalation carries any, and never on a personal-safety case
};

/**
 * The server's own sentences, oldest first, left as written: they name departments and never a member of staff.
 * A step with no note carries none — a personal-safety case has a note on none of its steps.
 */
export function timelineSteps(timeline: ReportTimelineEvent[] | undefined): TimelineStep[] {
  return (timeline ?? [])
    .filter((event) => event.description.trim() !== "")
    .map((event, index) => ({
      key: `${index}-${event.action}-${event.at}`,
      action: event.action,
      at: machineTime(event.at),
      when: formatDateTime(event.at),
      description: event.description.trim(),
      note: event.note?.trim() ? event.note.trim() : null,
      photos: event.photos ?? [],
    }));
}
