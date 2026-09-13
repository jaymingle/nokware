"use client";

import Link from "next/link";

import { ResponseCard } from "@/components/contributor/response-card";
import { SubmissionsTable } from "@/components/contributor/submissions-table";
import { EmptyPanel, ErrorPanel, LoadingPanel } from "@/components/documents/panels";
import { Button } from "@/components/ui/button";
import { useSubmissions } from "@/lib/api/queries";
import { awaitingResponse } from "@/lib/documents";

import type { DocumentOut } from "@/lib/api/types";

function NeedsResponse({ documents }: { documents: DocumentOut[] }) {
  return (
    <section aria-labelledby="needs-response" className="flex flex-col gap-3">
      <div>
        <h2 id="needs-response" className="text-[22px]">
          Needs your response
        </h2>
        <p className="text-[13.5px] text-ink-soft">
          A department disputed {documents.length === 1 ? "this document" : "these documents"}. Nothing happens until
          you respond.
        </p>
      </div>
      {documents.map((doc) => (
        <ResponseCard key={doc.id} doc={doc} />
      ))}
    </section>
  );
}

export function Submissions() {
  const { data, error, isPending, refetch } = useSubmissions();
  if (isPending) return <LoadingPanel label="Loading your submissions…" />;
  if (error) return <ErrorPanel message={error.message} onRetry={() => void refetch()} />;
  if (data.length === 0) {
    return (
      <EmptyPanel title="You haven't submitted anything yet">
        Submit a sourced document and the department it belongs to has 72 hours to review it.{" "}
        <Button variant="link" asChild className="h-auto p-0">
          <Link href="/portal/contributor/submit" data-testid="submissions-empty-submit">
            Submit a document
          </Link>
        </Button>
      </EmptyPanel>
    );
  }
  const disputed = awaitingResponse(data);
  return (
    <div className="flex flex-col gap-8">
      {disputed.length > 0 ? <NeedsResponse documents={disputed} /> : null}
      <SubmissionsTable documents={data} />
    </div>
  );
}
