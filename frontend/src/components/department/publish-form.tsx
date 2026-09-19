"use client";

import Link from "next/link";

import { CategoryField, SourceUrlField, TitleField, YearField } from "@/components/documents/document-fields";
import { ErrorNote } from "@/components/documents/panels";
import { PdfField } from "@/components/documents/pdf-field";
import { StatusTag } from "@/components/status-tag";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { usePdfForm } from "@/hooks/use-pdf-form";
import { useUploadDocument } from "@/lib/api/queries";
import { useMe } from "@/lib/auth/auth-context";
import { roleLabel } from "@/lib/portal/navigation";
import { ledgerStatus } from "@/lib/status";

import type { DocumentOut } from "@/lib/api/types";

function Published({ doc, onAnother }: { doc: DocumentOut; onAnother: () => void }) {
  return (
    <Card className="max-w-2xl border-teal" data-testid="publish-success">
      <CardContent className="flex flex-col gap-3">
        <div><StatusTag tone={ledgerStatus("published").tone}>{ledgerStatus("published").label}</StatusTag></div>
        <h2 className="text-[24px] leading-snug">{doc.title}</h2>
        <p className="text-sm text-ink-soft">
          It is in the public Ledger now, under {doc.department_name}&apos;s name, and will be answerable in Ask within
          minutes. The library shows when it becomes searchable.
        </p>
        <div className="flex flex-wrap gap-2 pt-1">
          <Button onClick={onAnother} data-testid="publish-another">
            Publish another
          </Button>
          <Button variant="secondary" asChild>
            <Link href="/portal/department/library" data-testid="publish-go-library">
              Go to the library
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/** A department publishes under its own name only; the server enforces it too. */
export function PublishForm() {
  const me = useMe();
  const upload = useUploadDocument();
  const { file, chooseFile, fileMissing, result, clearResult, onSubmit } = usePdfForm(upload.mutateAsync);
  if (result) {
    return <Published doc={result} onAnother={() => { clearResult(); upload.reset(); }} />;
  }
  return (
    <Card className="max-w-2xl">
      <CardContent>
        <form onSubmit={onSubmit} className="flex flex-col gap-5" data-testid="publish-form">
          <p className="text-sm">
            Publishing as <span className="font-medium">{roleLabel(me)}</span>. It goes into the Ledger straight away.
          </p>
          <PdfField file={file} onChange={chooseFile} testId="publish-file" />
          {fileMissing ? <ErrorNote>Choose the PDF to publish.</ErrorNote> : null}
          <TitleField />
          <CategoryField />
          <YearField />
          <SourceUrlField required={false} hint="Where else this document is published, if anywhere, e.g. ama.gov.gh." />
          {upload.error ? <ErrorNote>{upload.error.message}</ErrorNote> : null}
          <div>
            <Button type="submit" disabled={upload.isPending} data-testid="publish-submit">
              {upload.isPending ? "Publishing…" : "Publish"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
