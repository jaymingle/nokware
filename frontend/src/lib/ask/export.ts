import { env } from "@/lib/env";

import type { ExportFormat, ExportView } from "@/lib/api/types";

export const EXPORT_FORMATS: { format: ExportFormat; label: string }[] = [
  { format: "pdf", label: "PDF" },
  { format: "docx", label: "Word" },
  { format: "csv", label: "CSV" },
];

const MESSAGES: Record<number, string> = {
  403: "This answer can't be downloaded. Ask the question again to get one that can.",
  429: "That's a lot of downloads in an hour. Please try again later.",
};
export const EXPORT_FAILED = "The download didn't work. Please try again.";
export const EXPORT_OFFLINE = "Nokware can't be reached. Check your connection and try again.";

export class ExportError extends Error {}

/** The file name the API gave in Content-Disposition, or a plain one. */
export function filenameFrom(disposition: string | null, format: ExportFormat): string {
  const match = disposition?.match(/filename="([^"]+)"/);
  return match?.[1] ?? `nokware-answer.${format}`;
}

async function fetchExport(view: ExportView, format: ExportFormat): Promise<Response> {
  try {
    return await fetch(`${env.apiUrl}/api/ask/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ view, format }),
    });
  } catch {
    throw new ExportError(EXPORT_OFFLINE);
  }
}

/** Asks the API for the answer as a file (it renders only answers it signed), then saves it. */
export async function downloadAnswer(view: ExportView, format: ExportFormat): Promise<void> {
  const response = await fetchExport(view, format);
  if (!response.ok) throw new ExportError(MESSAGES[response.status] ?? EXPORT_FAILED);
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a");
  link.href = url;
  link.download = filenameFrom(response.headers.get("Content-Disposition"), format);
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
