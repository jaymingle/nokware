import { FileTextIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { env } from "@/lib/env";

/** Opens a published document's PDF; the API redirects to a fresh short-lived link. */
export function LedgerPdfLink({ documentId, testId }: { documentId: string; testId: string }) {
  return (
    <Button variant="secondary" size="sm" asChild>
      <a href={`${env.apiUrl}/api/ledger/${encodeURIComponent(documentId)}/file`} target="_blank" rel="noopener" data-testid={testId}>
        <FileTextIcon data-icon="inline-start" />
        View PDF
      </a>
    </Button>
  );
}
