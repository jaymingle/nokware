"use client";

import { useState } from "react";

import { CaseWorkspace } from "@/components/cases/case-workspace";
import { QueueToolbar } from "@/components/cases/queue-toolbar";
import { ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { useCaseQueue } from "@/lib/api/queries";
import { arrange, type MyFilterKey, type OrderKey } from "@/lib/cases";

const NOTHING = {
  all: "No cases right now. When a resident reports something that is yours to deal with, it appears here, most urgent first.",
  new: "Nothing new. Cases you haven't started yet appear here.",
  in_progress: "Nothing in progress. A case you have started appears here until you resolve it.",
  resolved: "Nothing resolved yet.",
} as const;

export function CaseQueue() {
  const { data, error, isPending, refetch } = useCaseQueue();
  const [filter, setFilter] = useState<MyFilterKey>("all");
  const [order, setOrder] = useState<OrderKey>("urgent");
  if (isPending) return <LoadingPanel label="Loading your cases…" />;
  if (error) return <ErrorPanel message={error.message} onRetry={() => void refetch()} />;
  return (
    <CaseWorkspace
      title="Case queue"
      cases={arrange(data.cases, filter, order)}
      toolbar={<QueueToolbar filter={filter} order={order} onFilter={setFilter} onOrder={setOrder} />}
      empty={NOTHING[filter]}
    />
  );
}
