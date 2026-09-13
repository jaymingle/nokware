"use client";

import { ResubmitDialog } from "@/components/contributor/resubmit-dialog";
import { ActionDialog } from "@/components/documents/action-dialog";
import { DocumentSummary } from "@/components/documents/document-summary";
import { ViewPdfButton } from "@/components/documents/view-pdf-button";
import { Card } from "@/components/ui/card";
import { formatDate } from "@/lib/time";

import type { DocumentOut } from "@/lib/api/types";

function DisputeDetails({ doc }: { doc: DocumentOut }) {
  const who = doc.disputed_by_name ?? doc.department_name ?? "The department";
  return (
    <div className="flex flex-col gap-1.5 rounded-lg bg-brick-tint px-4 py-3 text-[13.5px]" data-testid={`dispute-reason-${doc.id}`}>
      <p className="font-medium text-brick">
        Disputed by {who}
        {doc.disputed_at ? ` on ${formatDate(doc.disputed_at)}` : ""}
      </p>
      <p>{doc.dispute_reason}</p>
    </div>
  );
}

function WithdrawDialog({ doc }: { doc: DocumentOut }) {
  return (
    <ActionDialog
      doc={doc}
      action="accept-dispute"
      tone="destructive"
      triggerLabel="Accept the dispute"
      title="Accept the dispute and withdraw it?"
      description={`${doc.title} is withdrawn and stays out of the Ledger. This can't be undone.`}
      confirmLabel="Withdraw document"
      success="Withdrawn. It stays out of the Ledger."
    />
  );
}

function EscalateDialog({ doc }: { doc: DocumentOut }) {
  return (
    <ActionDialog
      doc={doc}
      action="escalate"
      tone="primary"
      triggerLabel="Escalate to the MCE"
      title="Escalate this dispute to the MCE"
      description={doc.title}
      confirmLabel="Escalate"
      note={{
        label: "Why should it be published?",
        hint: "The MCE sees the department's reason and yours, and has 72 hours to rule. If the MCE doesn't rule in time, it publishes automatically.",
        required: true,
      }}
      success="Escalated. The MCE has 72 hours to rule."
    />
  );
}

function ResponseActions({ doc }: { doc: DocumentOut }) {
  const allowed = new Set(doc.allowed_actions);
  return (
    <div className="flex flex-wrap gap-2 sm:ml-auto">
      {allowed.has("accept-dispute") ? <WithdrawDialog doc={doc} /> : null}
      {allowed.has("resubmit") ? <ResubmitDialog doc={doc} /> : null}
      {allowed.has("escalate") ? <EscalateDialog doc={doc} /> : null}
    </div>
  );
}

/** A disputed submission. Disputes have no clock: nothing happens until the contributor responds. */
export function ResponseCard({ doc }: { doc: DocumentOut }) {
  const used = doc.resubmission_count > 0;
  return (
    <Card className="gap-0 py-0" data-testid={`response-card-${doc.id}`}>
      <div className="flex flex-col gap-4 p-5">
        <DocumentSummary doc={doc} byline={`For ${doc.department_name ?? "the department"} · sent ${formatDate(doc.created_at)}`} />
        <DisputeDetails doc={doc} />
        <p className="text-[12.5px] text-ink-soft">
          It stays out of the Ledger until you respond: accept the dispute,
          {used ? " or escalate it to the MCE (you have used your one resubmission)." : " resubmit a corrected version once, or escalate it to the MCE."}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <ViewPdfButton documentId={doc.id} />
          <ResponseActions doc={doc} />
        </div>
      </div>
    </Card>
  );
}
