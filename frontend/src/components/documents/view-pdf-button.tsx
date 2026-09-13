import { FileTextIcon } from "lucide-react";

import { Button } from "@/components/ui/button";

/** Opens the document's current PDF in a new tab, via /file/[id] (which fetches a fresh short-lived link). */
export function ViewPdfButton({ documentId, label = "View PDF" }: { documentId: string; label?: string }) {
  return (
    <Button variant="secondary" asChild>
      <a href={`/file/${encodeURIComponent(documentId)}`} target="_blank" rel="noopener" data-testid={`view-pdf-${documentId}`}>
        <FileTextIcon data-icon="inline-start" />
        {label}
      </a>
    </Button>
  );
}
