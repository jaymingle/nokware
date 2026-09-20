import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";

import type { Sending } from "@/lib/api/upload";
import type { ReactNode } from "react";

export function FormSection({ title, hint, children }: { title: string; hint: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3 border-t pt-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-[17px]">{title}</h2>
        <p className="text-[12.5px] text-ink-soft">{hint}</p>
      </div>
      {children}
    </section>
  );
}

type FormActionsProps = { busy: boolean; error: Error | null; sending: Sending | null; onBack: () => void };

/** What is actually happening, and nothing more: the photos go first, and the API then reads and routes the report.
    Naming stages the browser can't see ("classifying", "routing") would be a guess dressed as progress. */
function sendingLabel(sending: Sending | null): string {
  if (sending === null || sending === "filing") return "Filing your report…";
  const percent = Math.round((sending.sent / Math.max(sending.total, 1)) * 100);
  return `Sending your photos… ${percent}%`;
}

export function FormActions({ busy, error, sending, onBack }: FormActionsProps) {
  return (
    <div className="flex flex-col gap-3">
      {error ? <ErrorNote testId="report-error">{error.message}</ErrorNote> : null}
      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" size="lg" disabled={busy} className="px-5" data-testid="report-submit">
          {busy ? "Filing…" : "File this report"}
        </Button>
        <Button type="button" variant="ghost" onClick={onBack} disabled={busy} data-testid="report-back">
          Back
        </Button>
        {busy ? (
          <span className="text-[12.5px] text-ink-soft" aria-live="polite" data-testid="report-progress">
            {sendingLabel(sending)}
          </span>
        ) : null}
      </div>
    </div>
  );
}
