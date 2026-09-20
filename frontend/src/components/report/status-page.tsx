"use client";

import { useState } from "react";

import { ErrorNote } from "@/components/documents/panels";
import { PageShell } from "@/components/page-shell";
import { QuickExit } from "@/components/report/quick-exit";
import { StatusLookup } from "@/components/report/status-lookup";
import { CivicStatus, PrivateStatus } from "@/components/report/status-view";
import { useForgetStatus, useReportStatus } from "@/lib/api/public-queries";

/** The reference is typed, never carried in the address. */
export function StatusPage() {
  const [reference, setReference] = useState<string | null>(null);
  const status = useReportStatus(reference);
  const forget = useForgetStatus();
  const clear = () => {
    if (reference) forget(reference);
    setReference(null);
  };
  return (
    <>
      {status.data?.private ? <QuickExit /> : null}
      <PageShell
        eyebrow="Report status"
        title="Follow a report"
        lead={
          <>
            Enter the reference you were given when you reported. It shows how far along the report is and, once it is
            resolved, what was done.
          </>
        }
      >
        <div className="flex flex-col gap-5">
          <StatusLookup busy={status.isFetching} showing={reference !== null} onLookup={setReference} onClear={clear} />
          {status.error ? <ErrorNote testId="status-error">{status.error.message}</ErrorNote> : null}
          {status.data ? status.data.private ? <PrivateStatus status={status.data} /> : <CivicStatus status={status.data} /> : null}
        </div>
      </PageShell>
    </>
  );
}
