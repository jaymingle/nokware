"use client";

import { OpenDisputes } from "@/components/department/open-disputes";
import { QueueSummary } from "@/components/department/queue-summary";
import { ReviewCard } from "@/components/department/review-card";
import { EmptyPanel, ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { useNow } from "@/hooks/use-now";
import { useReviewQueue } from "@/lib/api/queries";
import { splitHeld } from "@/lib/documents";

import type { DocumentOut } from "@/lib/api/types";

function CardList({ label, documents }: { label: string; documents: DocumentOut[] }) {
  return (
    <section aria-label={label} className="flex flex-col gap-4">
      {documents.map((doc) => (
        <ReviewCard key={doc.id} doc={doc} />
      ))}
    </section>
  );
}

export function ReviewQueue() {
  const now = useNow();
  const { data, error, isPending, refetch } = useReviewQueue();
  if (isPending) return <LoadingPanel label="Loading your review queue…" />;
  if (error) return <ErrorPanel message={error.message} onRetry={() => void refetch()} />;

  const { open, closed } = splitHeld(data, now);
  const disputed = data.filter((doc) => doc.status === "disputed");
  return (
    <div className="flex flex-col gap-8">
      <QueueSummary open={open} closed={closed.length} now={now} />
      {open.length > 0 ? (
        <CardList label="Awaiting your review" documents={open} />
      ) : (
        <EmptyPanel title="Nothing awaiting your review">
          When a contributor submits a document for your department, it appears here with the time left before it
          publishes automatically.
        </EmptyPanel>
      )}
      {closed.length > 0 ? <CardList label="Being published automatically" documents={closed} /> : null}
      {disputed.length > 0 ? <OpenDisputes documents={disputed} /> : null}
    </div>
  );
}
