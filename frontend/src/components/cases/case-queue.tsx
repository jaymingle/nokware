"use client";

import { CaseWorkspace } from "@/components/cases/case-workspace";
import { ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { useCaseQueue } from "@/lib/api/queries";

/** A department's or agency's cases: open work most severe and oldest first, then the last 30 days' resolved. */
export function CaseQueue() {
  const { data, error, isPending, refetch } = useCaseQueue();
  if (isPending) return <LoadingPanel label="Loading your cases…" />;
  if (error) return <ErrorPanel message={error.message} onRetry={() => void refetch()} />;
  return (
    <CaseWorkspace
      title="Case queue"
      cases={data.cases}
      empty="No cases right now. When a resident reports something that is yours to deal with, it appears here, most urgent first."
    />
  );
}
