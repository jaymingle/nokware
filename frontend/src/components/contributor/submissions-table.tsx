"use client";

import { DeadlineLine } from "@/components/documents/deadline-notice";
import { IngestionTag, Tag } from "@/components/documents/tag";
import { ViewPdfButton } from "@/components/documents/view-pdf-button";
import { Card } from "@/components/ui/card";
import { useNow } from "@/hooks/use-now";
import { describeSubmission } from "@/lib/documents";
import { formatDate } from "@/lib/time";

import type { DocumentOut } from "@/lib/api/types";

const TH = "border-b px-3 py-2.5 text-left text-[12.5px] font-medium text-ink-soft sm:px-4";
const TD = "border-b px-3 py-3.5 align-top sm:px-4";
const WIDE_ONLY = "hidden sm:table-cell"; // on phones these details move under the title

function ReviewCell({ doc, now }: { doc: DocumentOut; now: number }) {
  const view = describeSubmission(doc, now);
  return (
    <div className="flex flex-col items-start gap-1.5">
      <div className="flex flex-wrap gap-1.5">
        <Tag tone={view.tone} testId={`submission-status-${doc.id}`}>
          {view.label}
        </Tag>
        {doc.ingestion ? <IngestionTag state={doc.ingestion} /> : null}
      </div>
      {view.clock ? <DeadlineLine heldUntil={view.clock.heldUntil} unless={view.clock.unless} testId={`submission-clock-${doc.id}`} /> : null}
      {view.detail ? <p className="text-[12.5px] text-ink-soft">{view.detail}</p> : null}
    </div>
  );
}

function SubmissionRow({ doc, now }: { doc: DocumentOut; now: number }) {
  return (
    <tr className="transition-colors hover:bg-paper-subtle" data-testid={`submission-row-${doc.id}`}>
      <td className={TD}>
        <div className="text-[14.5px]">{doc.title}</div>
        <div className="text-[12px] text-ink-soft">{[doc.category, doc.document_year].filter(Boolean).join(" · ")}</div>
        <div className="text-[12px] text-ink-soft sm:hidden">
          {doc.department_name} · sent {formatDate(doc.created_at)}
        </div>
      </td>
      <td className={`${TD} ${WIDE_ONLY} text-[13px] text-ink-soft`}>{doc.department_name}</td>
      <td className={`${TD} ${WIDE_ONLY} text-[13px] whitespace-nowrap text-ink-soft tabular-nums`}>
        {formatDate(doc.created_at)}
      </td>
      <td className={TD}>
        <ReviewCell doc={doc} now={now} />
      </td>
      <td className={`${TD} text-right`}>
        <ViewPdfButton documentId={doc.id} label="PDF" compact />
      </td>
    </tr>
  );
}

/** Every submission, newest first, with where its review stands (the design's "My submissions"). */
export function SubmissionsTable({ documents }: { documents: DocumentOut[] }) {
  const now = useNow();
  return (
    <Card className="gap-0 py-0">
      <div className="border-b px-5 py-4">
        <h2 className="text-[19px]">My submissions</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse" data-testid="submissions-table">
          <thead>
            <tr>
              <th className={TH}>Document</th>
              <th className={`${TH} ${WIDE_ONLY} w-40`}>With</th>
              <th className={`${TH} ${WIDE_ONLY} w-28`}>Sent</th>
              <th className={`${TH} sm:w-80`}>Review</th>
              <th className={`${TH} sm:w-24`}>
                <span className="sr-only">File</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => (
              <SubmissionRow key={doc.id} doc={doc} now={now} />
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
