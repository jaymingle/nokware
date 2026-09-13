"use client";

import { useState } from "react";

import { EmptyPanel, ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { IngestionTag } from "@/components/documents/tag";
import { ViewPdfButton } from "@/components/documents/view-pdf-button";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { LIBRARY_PAGE_SIZE, useLibrary } from "@/lib/api/queries";
import { formatDate } from "@/lib/time";

import type { DocumentOut } from "@/lib/api/types";

const TH = "border-b px-3 py-2.5 text-left text-[12.5px] font-medium text-ink-soft sm:px-4";
const TD = "border-b px-3 py-3.5 align-top sm:px-4";
const WIDE_ONLY = "hidden sm:table-cell"; // on phones these details move under the title

function LibraryRow({ doc }: { doc: DocumentOut }) {
  return (
    <tr className="transition-colors hover:bg-paper-subtle" data-testid={`library-row-${doc.id}`}>
      <td className={TD}>
        <div className="text-[14.5px]">{doc.title}</div>
        <div className="text-[12px] text-ink-soft">{[doc.category, doc.document_year].filter(Boolean).join(" · ")}</div>
        <div className="text-[12px] text-ink-soft sm:hidden">{doc.published_at ? `Published ${formatDate(doc.published_at)}` : ""}</div>
      </td>
      <td className={`${TD} ${WIDE_ONLY} text-[13px] text-ink-soft`}>
        {doc.source_type === "contributor" ? "Contributor" : "Department"}
      </td>
      <td className={`${TD} ${WIDE_ONLY} text-[13px] whitespace-nowrap text-ink-soft tabular-nums`}>
        {doc.published_at ? formatDate(doc.published_at) : ""}
      </td>
      <td className={TD}>{doc.ingestion ? <IngestionTag state={doc.ingestion} testId={`ingestion-${doc.id}`} /> : null}</td>
      <td className={`${TD} text-right`}>
        <ViewPdfButton documentId={doc.id} label="PDF" compact />
      </td>
    </tr>
  );
}

function Pager({ page, total, busy, onPage }: { page: number; total: number; busy: boolean; onPage: (page: number) => void }) {
  const first = page * LIBRARY_PAGE_SIZE + 1;
  const last = Math.min(total, (page + 1) * LIBRARY_PAGE_SIZE);
  return (
    <div className="flex flex-wrap items-center gap-3 px-5 py-3.5">
      <p className="mr-auto text-[12.5px] text-ink-soft tabular-nums" data-testid="library-range">
        {first}–{last} of {total}
      </p>
      <Button variant="secondary" size="sm" disabled={page === 0 || busy} onClick={() => onPage(page - 1)} data-testid="library-previous">
        Previous
      </Button>
      <Button variant="secondary" size="sm" disabled={last >= total || busy} onClick={() => onPage(page + 1)} data-testid="library-next">
        Next
      </Button>
    </div>
  );
}

export function LibraryTable() {
  const [page, setPage] = useState(0);
  const { data, error, isPending, isPlaceholderData, refetch } = useLibrary(page);
  if (isPending) return <LoadingPanel label="Loading the library…" />;
  if (error) return <ErrorPanel message={error.message} onRetry={() => void refetch()} />;
  if (data.total === 0) {
    return <EmptyPanel title="Nothing published yet">Documents your department publishes, or accepts from contributors, appear here.</EmptyPanel>;
  }
  return (
    <Card className="gap-0 py-0">
      <div className="overflow-x-auto">
        <table className="w-full border-collapse" data-testid="library-table">
          <thead>
            <tr>
              <th className={TH}>Document</th>
              <th className={`${TH} ${WIDE_ONLY} w-32`}>Source</th>
              <th className={`${TH} ${WIDE_ONLY} w-32`}>Published</th>
              <th className={`${TH} sm:w-52`}>In Ask</th>
              <th className={`${TH} sm:w-24`}><span className="sr-only">File</span></th>
            </tr>
          </thead>
          <tbody>
            {data.documents.map((doc) => (
              <LibraryRow key={doc.id} doc={doc} />
            ))}
          </tbody>
        </table>
      </div>
      <Pager page={page} total={data.total} busy={isPlaceholderData} onPage={setPage} />
    </Card>
  );
}
