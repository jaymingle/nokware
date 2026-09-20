import { FileTextIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ledgerFileUrl } from "@/lib/api/public";

/** The API redirects to a fresh short-lived link. */
export function LedgerPdfLink({ documentId, testId }: { documentId: string; testId: string }) {
  return (
    <Button variant="secondary" size="sm" asChild>
      <a href={ledgerFileUrl(documentId)} target="_blank" rel="noopener" data-testid={testId}>
        <FileTextIcon data-icon="inline-start" />
        View PDF
      </a>
    </Button>
  );
}
