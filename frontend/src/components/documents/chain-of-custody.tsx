"use client";

import { ChevronRightIcon } from "lucide-react";
import { useState } from "react";

import { ErrorNote } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { useDocumentDetail } from "@/lib/api/queries";
import { historyActor, historyLabel } from "@/lib/history";
import { formatDateTime } from "@/lib/time";

import type { HistoryEntry } from "@/lib/api/types";

function TrailEntry({ entry }: { entry: HistoryEntry }) {
  const who = [historyActor(entry), formatDateTime(entry.at)].filter(Boolean).join(" · ");
  return (
    <li className="grid grid-cols-[12px_minmax(0,1fr)] gap-2.5 pb-3.5 last:pb-0">
      <span aria-hidden className="mt-[7px] size-[5px] rounded-full bg-teal" />
      <div>
        <p className="text-[13px]">{historyLabel(entry.action)}</p>
        <p className="text-[12px] text-ink-soft tabular-nums">{who}</p>
        {entry.note ? <p className="mt-1 text-[12.5px] text-ink-soft">&ldquo;{entry.note}&rdquo;</p> : null}
      </div>
    </li>
  );
}

function Trail({ documentId }: { documentId: string }) {
  const { data, error, isPending, refetch } = useDocumentDetail(documentId, true);
  if (isPending) return <p className="text-[12.5px] text-ink-soft">Loading the trail…</p>;
  if (error) {
    return (
      <div className="flex flex-wrap items-center gap-3">
        <ErrorNote>{error.message}</ErrorNote>
        <Button variant="secondary" size="sm" onClick={() => void refetch()} data-testid={`custody-retry-${documentId}`}>
          Try again
        </Button>
      </div>
    );
  }
  return (
    <ol data-testid={`custody-trail-${documentId}`}>
      {data.history.map((entry) => (
        <TrailEntry key={`${entry.at}-${entry.action}`} entry={entry} />
      ))}
    </ol>
  );
}

export function ChainOfCustody({ documentId }: { documentId: string }) {
  const [open, setOpen] = useState(false);
  return (
    <details className="group" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary
        className="flex w-fit cursor-pointer list-none items-center gap-1.5 text-[12.5px] text-ink-soft hover:text-ink [&::-webkit-details-marker]:hidden"
        data-testid={`custody-toggle-${documentId}`}
      >
        <ChevronRightIcon aria-hidden className="size-3.5 transition-transform group-open:rotate-90" />
        Chain of custody
      </summary>
      {open ? (
        <div className="mt-3 pl-1">
          <Trail documentId={documentId} />
        </div>
      ) : null}
    </details>
  );
}
