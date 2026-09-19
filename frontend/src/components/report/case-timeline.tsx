import { timelineSteps } from "@/lib/report/timeline";

import type { ReportTimelineEvent } from "@/lib/api/types";
import type { TimelineStep } from "@/lib/report/timeline";

function Step({ step, connected }: { step: TimelineStep; connected: boolean }) {
  return (
    <li className="relative flex flex-col gap-1 pb-5 pl-6 last:pb-0" data-testid="status-timeline-step">
      {connected ? <span aria-hidden className="absolute top-2 left-[3.5px] h-full w-px bg-hairline" /> : null}
      <span aria-hidden className="absolute top-1.5 left-0 size-2 rounded-full bg-teal" />
      <time dateTime={step.at} className="text-[12.5px] text-ink-soft tabular-nums">{step.when}</time>
      <p className="text-[14.5px]">{step.description}</p>
      {step.note ? (
        <p className="mt-0.5 rounded-lg bg-paper-subtle px-3.5 py-2.5 text-[13.5px] whitespace-pre-line" data-testid="status-timeline-note">
          {step.note}
        </p>
      ) : null}
    </li>
  );
}

/** The whole case, oldest first, in the server's own words. Nothing stands in for a step that has no note. */
export function CaseTimeline({ timeline }: { timeline?: ReportTimelineEvent[] }) {
  const steps = timelineSteps(timeline);
  if (steps.length === 0) return null;
  return (
    <section className="flex flex-col gap-3 border-t pt-5" aria-labelledby="status-timeline-heading" data-testid="status-timeline">
      <h3 id="status-timeline-heading" className="text-[15px]">What has happened</h3>
      <ol className="flex flex-col">
        {steps.map((step, index) => (
          <Step key={step.key} step={step} connected={index < steps.length - 1} />
        ))}
      </ol>
    </section>
  );
}
