"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";

import { CategoryField, SourceUrlField, TitleField, YearField } from "@/components/documents/document-fields";
import { ErrorNote } from "@/components/documents/panels";
import { PdfField } from "@/components/documents/pdf-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useMe } from "@/lib/auth/auth-context";
import { useUploadDocument } from "@/lib/api/queries";
import { roleLabel } from "@/lib/portal/navigation";

import type { DocumentOut } from "@/lib/api/types";

function Published({ doc, onAnother }: { doc: DocumentOut; onAnother: () => void }) {
  return (
    <Card className="max-w-2xl border-teal" data-testid="publish-success">
      <CardContent className="flex flex-col gap-3">
        <p className="text-[12.5px] text-teal">Published</p>
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

function usePublish() {
  const upload = useUploadDocument();
  const [file, setFile] = useState<File | null>(null);
  const [fileMissing, setFileMissing] = useState(false);
  const [published, setPublished] = useState<DocumentOut | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setFileMissing(true);
      return;
    }
    const form = new FormData(event.currentTarget);
    form.set("file", file);
    try {
      setPublished(await upload.mutateAsync(form));
      setFile(null);
    } catch {
      // upload.error is shown below the form
    }
  }

  const chooseFile = (next: File | null) => {
    setFile(next);
    setFileMissing(false);
  };
  const startOver = () => {
    setPublished(null);
    upload.reset();
  };
  return { upload, file, chooseFile, fileMissing, published, startOver, onSubmit };
}

/** A department publishes under its own name only; the server enforces it too. */
export function PublishForm() {
  const me = useMe();
  const { upload, file, chooseFile, fileMissing, published, startOver, onSubmit } = usePublish();
  if (published) return <Published doc={published} onAnother={startOver} />;
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
