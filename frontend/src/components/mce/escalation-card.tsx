"use client";

import { ActionDialog } from "@/components/documents/action-dialog";
import { ChainOfCustody } from "@/components/documents/chain-of-custody";
import { DeadlineNotice } from "@/components/documents/deadline-notice";
import { DocumentSummary } from "@/components/documents/document-summary";
import { ViewPdfButton } from "@/components/documents/view-pdf-button";
import { Card } from "@/components/ui/card";
import { useNow } from "@/hooks/use-now";
import { clockRunning } from "@/lib/documents";
import { formatDate } from "@/lib/time";

import type { DocumentOut } from "@/lib/api/types";

const RULING_NOTE = {
  label: "Your reasoning (optional)",
  hint: "Written to the audit trail with your name and the time.",
  required: false,
};

/** The department's reason for disputing it, beside the contributor's case for publishing it. */
function BothSides({ doc }: { doc: DocumentOut }) {
  const department = doc.department_name ?? "The department";
  const disputedBy = [doc.disputed_by_name ?? department, doc.disputed_at ? formatDate(doc.disputed_at) : null];
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div className="flex flex-col gap-1.5 rounded-lg bg-brick-tint px-4 py-3 text-[13.5px]" data-testid={`mce-dispute-${doc.id}`}>
        <p className="font-medium text-brick">{department}&apos;s dispute</p>
        <p>{doc.dispute_reason}</p>
        <p className="text-[12px] text-ink-soft">{disputedBy.filter(Boolean).join(" · ")}</p>
      </div>
      <div className="flex flex-col gap-1.5 rounded-lg bg-paper-subtle px-4 py-3 text-[13.5px]" data-testid={`mce-response-${doc.id}`}>
        <p className="font-medium">{doc.uploaded_by_name ?? "The contributor"}&apos;s case for publishing</p>
        <p>{doc.contributor_response}</p>
      </div>
    </div>
  );
}

function Rulings({ doc }: { doc: DocumentOut }) {
  const allowed = new Set(doc.allowed_actions);
  const department = doc.department_name ?? "the department";
  return (
    <div className="flex flex-wrap gap-2 sm:ml-auto">
      {allowed.has("uphold") ? (
        <ActionDialog
          doc={doc}
          action="uphold"
          tone="destructive"
          triggerLabel="Uphold the dispute"
          title="Uphold the dispute?"
          description={`${department}'s dispute stands: ${doc.title} is withdrawn and stays out of the Ledger. This can't be undone.`}
          confirmLabel="Uphold and withdraw"
          note={RULING_NOTE}
          success="Dispute upheld. The document is withdrawn."
        />
      ) : null}
      {allowed.has("overrule") ? (
        <ActionDialog
          doc={doc}
          action="overrule"
          tone="primary"
          triggerLabel="Overrule and publish"
          title="Overrule the dispute and publish?"
          description={`${doc.title} goes into ${department}'s public record and becomes answerable in Ask within minutes. This can't be undone.`}
          confirmLabel="Overrule and publish"
          note={RULING_NOTE}
          success="Overruled. It will be answerable in Ask within minutes."
        />
      ) : null}
    </div>
  );
}

/** A dispute escalated to the MCE, led by the MCE's clock. */
export function EscalationCard({ doc }: { doc: DocumentOut }) {
  const open = clockRunning(doc, useNow());
  const byline = `Submitted by ${doc.uploaded_by_name ?? "a contributor"} to ${doc.department_name ?? "a department"} on ${formatDate(doc.created_at)}`;
  return (
    <Card className="gap-0 py-0" data-testid={`escalation-card-${doc.id}`}>
      {doc.held_until ? (
        <DeadlineNotice heldUntil={doc.held_until} unless="you uphold the dispute" testId={`mce-deadline-${doc.id}`} />
      ) : null}
      <div className="flex flex-col gap-4 p-5">
        <DocumentSummary doc={doc} byline={byline} />
        <BothSides doc={doc} />
        {doc.resubmission_count > 0 ? (
          <p className="text-[12.5px] text-ink-soft">
            This is the revised version: the contributor resubmitted it once after an earlier dispute.
          </p>
        ) : null}
        <ChainOfCustody documentId={doc.id} />
        <div className="flex flex-wrap items-center gap-2">
          <ViewPdfButton documentId={doc.id} />
          {open ? <Rulings doc={doc} /> : null}
        </div>
      </div>
    </Card>
  );
}
