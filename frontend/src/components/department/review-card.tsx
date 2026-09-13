"use client";

import { ActionDialog } from "@/components/documents/action-dialog";
import { DeadlineNotice } from "@/components/documents/deadline-notice";
import { DocumentSummary } from "@/components/documents/document-summary";
import { ViewPdfButton } from "@/components/documents/view-pdf-button";
import { Card } from "@/components/ui/card";
import { useNow } from "@/hooks/use-now";
import { clockRunning } from "@/lib/documents";
import { formatDate } from "@/lib/time";

import type { DocumentOut } from "@/lib/api/types";

function ResubmissionNote({ doc }: { doc: DocumentOut }) {
  return (
    <div className="flex flex-col gap-1.5 rounded-lg bg-paper-subtle px-4 py-3 text-[13.5px]" data-testid={`resubmission-${doc.id}`}>
      <p className="font-medium">Resubmitted after your dispute</p>
      {doc.dispute_reason ? <p className="text-ink-soft">Your dispute: {doc.dispute_reason}</p> : null}
      {doc.contributor_response ? <p className="text-ink-soft">Contributor&apos;s note: {doc.contributor_response}</p> : null}
    </div>
  );
}

function ReviewActions({ doc }: { doc: DocumentOut }) {
  const allowed = new Set(doc.allowed_actions);
  const department = doc.department_name ?? "your department";
  return (
    <div className="flex flex-wrap gap-2 sm:ml-auto">
      {allowed.has("dispute") ? (
        <ActionDialog
          doc={doc}
          action="dispute"
          tone="destructive"
          triggerLabel="Dispute"
          title="Dispute this document"
          description={doc.title}
          confirmLabel="Dispute document"
          note={{
            label: "Why are you disputing it?",
            hint: "The contributor sees this. They can withdraw the document, resubmit it once, or escalate to the MCE. Until then it stays out of the Ledger.",
            required: true,
          }}
          success="Disputed. The document stays out of the Ledger until the contributor responds."
        />
      ) : null}
      {allowed.has("accept") ? (
        <ActionDialog
          doc={doc}
          action="accept"
          tone="primary"
          triggerLabel="Accept and publish now"
          title="Publish this document now?"
          description={`${doc.title} becomes answerable in Ask within minutes, under ${department}'s name. Publishing can't be undone.`}
          confirmLabel="Publish now"
          success="Published. It will be answerable in Ask within minutes."
        />
      ) : null}
    </div>
  );
}

/** A contributor's document awaiting this department's review, led by its clock. */
export function ReviewCard({ doc }: { doc: DocumentOut }) {
  const now = useNow();
  const open = clockRunning(doc, now);
  const byline = `Submitted by ${doc.uploaded_by_name ?? "a contributor"} on ${formatDate(doc.created_at)}`;
  return (
    <Card className="gap-0 py-0" data-testid={`review-card-${doc.id}`}>
      {doc.held_until ? (
        <DeadlineNotice heldUntil={doc.held_until} unless="you dispute it" testId={`deadline-${doc.id}`} />
      ) : null}
      <div className="flex flex-col gap-4 p-5">
        <DocumentSummary doc={doc} byline={byline} />
        {doc.resubmission_count > 0 ? <ResubmissionNote doc={doc} /> : null}
        <div className="flex flex-wrap items-center gap-2">
          <ViewPdfButton documentId={doc.id} />
          {open ? <ReviewActions doc={doc} /> : null}
        </div>
      </div>
    </Card>
  );
}
