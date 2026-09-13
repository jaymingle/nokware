import { FileTextIcon } from "lucide-react";

import { Button } from "@/components/ui/button";

type ViewPdfButtonProps = {
  documentId: string;
  label?: string;
  /** Icon only on phones (the label stays for screen readers), for table rows. */
  compact?: boolean;
};

/** Opens the document's current PDF in a new tab, via /file/[id] (which fetches a fresh short-lived link). */
export function ViewPdfButton({ documentId, label = "View PDF", compact = false }: ViewPdfButtonProps) {
  return (
    <Button variant="secondary" asChild>
      <a href={`/file/${encodeURIComponent(documentId)}`} target="_blank" rel="noopener" data-testid={`view-pdf-${documentId}`}>
        <FileTextIcon data-icon="inline-start" />
        <span className={compact ? "sr-only sm:not-sr-only" : undefined}>{label}</span>
      </a>
    </Button>
  );
}
