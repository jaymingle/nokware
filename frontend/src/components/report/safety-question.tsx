import { ArrowRightIcon } from "lucide-react";

import { EmergencyNote } from "@/components/report/notes";

function Choice({ title, body, onClick, testId }: { title: string; body: string; onClick: () => void; testId: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex h-full flex-col items-start gap-2 rounded-xl border bg-card p-5 text-left transition-colors hover:border-teal focus-visible:border-teal focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
      data-testid={testId}
    >
      <span className="text-[18px] font-medium leading-snug">{title}</span>
      <span className="text-[14px] text-ink-soft">{body}</span>
      <ArrowRightIcon aria-hidden className="mt-auto size-4 text-teal transition-transform group-hover:translate-x-0.5" />
    </button>
  );
}

/** The first question: a report about someone's safety takes a private path from the start. */
export function SafetyQuestion({ onChoose }: { onChoose: (safety: boolean) => void }) {
  return (
    <section aria-labelledby="safety-question" className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <h2 id="safety-question" className="text-[24px] leading-snug">
          Is someone&apos;s safety at risk?
        </h2>
        <p className="max-w-[62ch] text-[14.5px] text-ink-soft">
          If a person is being hurt or threatened, choose yes. That report goes only to the services that protect
          people, never appears on the public dashboard, and is not read by an AI model.
        </p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Choice
          title="No, it's a problem in my area"
          body="A blocked drain, uncollected refuse, a pothole, a broken streetlight, a fire hazard."
          onClick={() => onChoose(false)}
          testId="report-choose-civic"
        />
        <Choice
          title="Yes, someone is in danger"
          body="Someone is being hurt, a child is at risk, or someone's life has been threatened."
          onClick={() => onChoose(true)}
          testId="report-choose-safety"
        />
      </div>
      <EmergencyNote />
    </section>
  );
}
