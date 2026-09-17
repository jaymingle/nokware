"use client";

import Link from "next/link";

import {
  CategoryField,
  DepartmentField,
  SourceUrlField,
  TitleField,
  YearField,
} from "@/components/documents/document-fields";
import { ErrorNote } from "@/components/documents/panels";
import { PdfField } from "@/components/documents/pdf-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { usePdfForm } from "@/hooks/use-pdf-form";
import { useUploadDocument } from "@/lib/api/queries";
import { formatDateTime } from "@/lib/time";

import type { DocumentOut } from "@/lib/api/types";

function Submitted({ doc, onAnother }: { doc: DocumentOut; onAnother: () => void }) {
  const department = doc.department_name ?? "The department";
  return (
    <Card className="max-w-2xl border-teal" data-testid="submit-success">
      <CardContent className="flex flex-col gap-3">
        <p className="text-[12.5px] text-teal">Submitted to {department}</p>
        <h2 className="text-[24px] leading-snug">{doc.title}</h2>
        <p className="text-sm text-ink-soft">
          It is held out of the Ledger while {department} reviews it.
          {doc.held_until
            ? ` Unless ${department} disputes it by ${formatDateTime(doc.held_until)}, it publishes automatically.`
            : ""}
        </p>
        <div className="flex flex-wrap gap-2 pt-1">
          <Button onClick={onAnother} data-testid="submit-another">
            Submit another
          </Button>
          <Button variant="secondary" asChild>
            <Link href="/portal/contributor" data-testid="submit-go-submissions">
              See my submissions
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function SubmitForm() {
  const upload = useUploadDocument();
  const { file, chooseFile, fileMissing, result, clearResult, onSubmit } = usePdfForm(upload.mutateAsync);
  if (result) {
    return <Submitted doc={result} onAnother={() => { clearResult(); upload.reset(); }} />;
  }
  return (
    <Card className="max-w-2xl">
      <CardContent>
        <form onSubmit={onSubmit} className="flex flex-col gap-5" data-testid="submit-form">
          <PdfField file={file} onChange={chooseFile} testId="submit-file" />
          {fileMissing ? <ErrorNote>Choose the PDF to submit.</ErrorNote> : null}
          <DepartmentField />
          <TitleField />
          <CategoryField />
          <YearField />
          <SourceUrlField required hint="The public web address where you found this document, so the department can check it." />
          {upload.error ? <ErrorNote>{upload.error.message}</ErrorNote> : null}
          <div>
            <Button type="submit" disabled={upload.isPending} data-testid="submit-submit">
              {upload.isPending ? "Submitting…" : "Submit for review"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
