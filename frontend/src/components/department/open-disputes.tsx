import { DeadlineNotice } from "@/components/documents/deadline-notice";
import { DocumentSummary } from "@/components/documents/document-summary";
import { Tag } from "@/components/documents/tag";
import { ViewPdfButton } from "@/components/documents/view-pdf-button";
import { Card } from "@/components/ui/card";
import { formatDate } from "@/lib/time";

import type { DocumentOut } from "@/lib/api/types";

function DisputeCard({ doc }: { doc: DocumentOut }) {
  const escalated = doc.escalated_to_mce;
  return (
    <Card className="gap-0 py-0" data-testid={`dispute-card-${doc.id}`}>
      {escalated && doc.held_until ? (
        <DeadlineNotice heldUntil={doc.held_until} unless="the MCE upholds your dispute" size="sm" />
      ) : null}
      <div className="flex flex-col gap-3 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <DocumentSummary doc={doc} byline={`Disputed ${doc.disputed_at ? formatDate(doc.disputed_at) : ""}`.trim()} />
          <Tag tone={escalated ? "gold" : "neutral"}>{escalated ? "With the MCE" : "Waiting for the contributor"}</Tag>
        </div>
        <div className="flex flex-col gap-1 text-[13.5px] text-ink-soft">
          {doc.dispute_reason ? <p>Your reason: {doc.dispute_reason}</p> : null}
          {doc.contributor_response ? <p>Contributor&apos;s response: {doc.contributor_response}</p> : null}
        </div>
        <div>
          <ViewPdfButton documentId={doc.id} />
        </div>
      </div>
    </Card>
  );
}

export function OpenDisputes({ documents }: { documents: DocumentOut[] }) {
  return (
    <section aria-labelledby="open-disputes" className="flex flex-col gap-3">
      <div>
        <h2 id="open-disputes" className="text-[22px]">
          Your open disputes
        </h2>
        <p className="text-[13.5px] text-ink-soft">
          Held out of the Ledger. A dispute waits for the contributor; once escalated, the MCE has 72 hours to rule.
        </p>
      </div>
      {documents.map((doc) => (
        <DisputeCard key={doc.id} doc={doc} />
      ))}
    </section>
  );
}
