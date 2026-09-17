import type { PetitionModeration } from "@/lib/api/types";

function Figure({ value, label, testId }: { value: number; label: string; testId: string }) {
  return (
    <div className="flex flex-col gap-0.5" data-testid={testId}>
      <span className="font-heading text-[26px] leading-none tabular-nums">{value.toLocaleString()}</span>
      <span className="text-[12.5px] text-ink-soft">{label}</span>
    </div>
  );
}

/**
 * The MCE is usually a petition's target, so every refusal is counted by its reason, and petitions left undecided
 * are counted as publishing themselves.
 */
export function ModerationRecord({ moderation }: { moderation: PetitionModeration }) {
  return (
    <section aria-labelledby="moderation-title" className="flex flex-col gap-4 rounded-xl border bg-card p-5" data-testid="petition-moderation">
      <div className="flex flex-col gap-1">
        <h2 id="moderation-title" className="text-[19px]">How the MCE has handled petitions</h2>
        <p className="max-w-[70ch] text-[13px] text-ink-soft">
          Every petition goes to the MCE first. They can publish it, or refuse it only for one of the reasons below. If they
          don&apos;t decide within 72 hours, it publishes automatically. These are exact counts of the MCE&apos;s decisions.
        </p>
      </div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <Figure value={moderation.awaiting} label="Waiting for review" testId="moderation-awaiting" />
        <Figure value={moderation.published_by_mce} label="Published by the MCE" testId="moderation-published" />
        <Figure value={moderation.published_automatically} label="Published automatically after 72 hours" testId="moderation-automatic" />
        <Figure value={moderation.refusals_total} label="Refused" testId="moderation-refused" />
      </div>
      <div className="flex flex-col gap-1.5">
        <h3 className="text-[13.5px] font-medium">Refusals by reason</h3>
        <ul className="grid gap-x-6 gap-y-1 text-[13px] sm:grid-cols-2">
          {moderation.refusals.map((refusal) => (
            <li key={refusal.reason} className="flex justify-between gap-3 border-b border-dashed py-1" data-testid={`moderation-reason-${refusal.reason}`}>
              <span>{refusal.label}</span>
              <span className="tabular-nums">{refusal.count}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
