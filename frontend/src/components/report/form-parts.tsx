import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";

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

type FormActionsProps = { busy: boolean; error: Error | null; onBack: () => void };

/** Filing waits on the classifier, so the wait is explained. */
export function FormActions({ busy, error, onBack }: FormActionsProps) {
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
          <span className="text-[12.5px] text-ink-soft" aria-live="polite">
            This can take a few seconds.
          </span>
        ) : null}
      </div>
    </div>
  );
}
