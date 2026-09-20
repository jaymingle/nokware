import { RtiPanel } from "@/components/ask/rti-panel";

export function NoInformation({ testIdPrefix }: { testIdPrefix: string }) {
  return (
    <div className="flex flex-col gap-4" data-testid={`${testIdPrefix}-no-information`}>
      <div className="flex flex-col gap-1.5">
        <h3 className="text-[18px] leading-snug">The Ledger doesn&apos;t hold an answer to this yet</h3>
        <p className="text-[14.5px] text-ink-soft">
          Nokware answers only from documents the Assembly has published here, and it found nothing that answers
          this. If you think a document should, try again with its name, the department or the year.
        </p>
      </div>
      <div className="border-t pt-4">
        <RtiPanel testId={`${testIdPrefix}-rti`} />
      </div>
    </div>
  );
}
