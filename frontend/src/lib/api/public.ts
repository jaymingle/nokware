// The API's public routes: no sign-in, so this never loads the auth client.
import { ApiError, UNREACHABLE, errorMessage } from "@/lib/api/errors";
import { env } from "@/lib/env";

import type {
  ContactDirectory,
  Dashboard,
  IssuePage,
  PreferencesResult,
  PublishingRecord,
  ReportOptions,
  ReportPreferences,
  ReportReceipt,
  ReportStatus,
  Representation,
  Responsiveness,
  VoiceResult,
} from "@/lib/api/types";

export async function publicRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${env.apiUrl}${path}`, init);
  } catch {
    throw new ApiError(0, UNREACHABLE);
  }
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  return (await response.json()) as T;
}

export function postJson<T>(path: string, body: unknown, headers: Record<string, string> = {}): Promise<T> {
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

/** What the Assembly is required to publish, against what the Ledger holds, by year. */
export function getPublishingRecord(): Promise<PublishingRecord> {
  return publicRequest<PublishingRecord>("/api/publishing-record");
}

/** Each Assembly department's handling of reports and contributors' documents over the last twelve months. */
export function getResponsiveness(): Promise<Responsiveness> {
  return publicRequest<Responsiveness>("/api/responsiveness");
}

export function getContacts(): Promise<ContactDirectory> {
  return publicRequest<ContactDirectory>("/api/contacts");
}

/** Every sub-metro with its chairperson, office and electoral areas. */
export function getRepresentatives(): Promise<Representation> {
  return publicRequest<Representation>("/api/representatives");
}

export type IssueFilters = { subMetro: string; topic: string; limit: number; offset: number };

/** Open civic issues, most supported first. */
export function getIssues({ subMetro, topic, limit, offset }: IssueFilters): Promise<IssuePage> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (subMetro) params.set("sub_metro", subMetro);
  if (topic) params.set("topic", topic);
  return publicRequest<IssuePage>(`/api/issues?${params}`);
}

/** Add this browser's voice to an issue: anonymous unless a name is given. */
export function addVoice(publicId: string, deviceToken: string, name: string | null): Promise<VoiceResult> {
  return postJson<VoiceResult>(`/api/issues/${encodeURIComponent(publicId)}/voices`, { device_token: deviceToken, name });
}
