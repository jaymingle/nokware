/** Matches the API's limit; the server checks again. */
export const MAX_PDF_BYTES = 50 * 1024 * 1024;

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Why a chosen file can't be uploaded, or null if it can. */
export function pdfProblem(file: Pick<File, "name" | "type" | "size">): string | null {
  const looksLikePdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!looksLikePdf) return "Choose a PDF file.";
  if (file.size === 0) return "That file is empty.";
  if (file.size > MAX_PDF_BYTES) return `That PDF is ${formatBytes(file.size)}; the limit is 50 MB.`;
  return null;
}
