// The API's public routes: no sign-in, so this never loads the auth client.
import { ApiError, UNREACHABLE, errorMessage } from "@/lib/api/errors";
import { env } from "@/lib/env";

import type {
  ContactDirectory,
  Dashboard,
  PreferencesResult,
  ReportOptions,
  ReportPreferences,
  ReportReceipt,
  ReportStatus,
} from "@/lib/api/types";

async function publicRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${env.apiUrl}${path}`, init);
  } catch {
    throw new ApiError(0, UNREACHABLE);
  }
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  return (await response.json()) as T;
}

function postJson<T>(path: string, body: unknown, headers: Record<string, string> = {}): Promise<T> {
  return publicRequest<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

/** A published document's PDF: the API redirects to a fresh short-lived link. */
export function ledgerFileUrl(documentId: string): string {
  return `${env.apiUrl}/api/ledger/${encodeURIComponent(documentId)}/file`;
}

const reportPath = (reference: string) => `/api/reports/${encodeURIComponent(reference)}`;

export function getReportOptions(): Promise<ReportOptions> {
  return publicRequest<ReportOptions>("/api/reports/options");
}

/** A multipart report: the fields plus up to 10 "photos". */
export function fileReport(form: FormData): Promise<ReportReceipt> {
  return publicRequest<ReportReceipt>("/api/reports", { method: "POST", body: form });
}

export function getReportStatus(reference: string): Promise<ReportStatus> {
  return publicRequest<ReportStatus>(reportPath(reference));
}

export function escalateReport(reference: string, note: string): Promise<ReportStatus> {
  return postJson<ReportStatus>(`${reportPath(reference)}/escalate`, { note });
}

/** The one-time answer about messages and calls, with the token from the receipt. */
export function setReportPreferences(reference: string, token: string, choice: ReportPreferences): Promise<PreferencesResult> {
  return postJson<PreferencesResult>(`${reportPath(reference)}/preferences`, choice, { "X-Receipt-Token": token });
}

export function getDashboard(): Promise<Dashboard> {
  return publicRequest<Dashboard>("/api/dashboard");
}

export function getContacts(): Promise<ContactDirectory> {
  return publicRequest<ContactDirectory>("/api/contacts");
}
