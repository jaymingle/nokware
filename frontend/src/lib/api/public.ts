// The API's public routes: no sign-in, so this never loads the auth client.
import { ApiError, UNREACHABLE, errorMessage } from "@/lib/api/errors";
import { timedOut, timedOutMessage, withTimeout } from "@/lib/api/timeout";
import { postWithProgress, type Sending } from "@/lib/api/upload";
import { env } from "@/lib/env";

import type {
  AskHeard,
  ContactDirectory,
  Dashboard,
  ExportView,
  Issue,
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

async function publicFetch(path: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${env.apiUrl}${path}`, withTimeout(init));
  } catch (error) {
    const late = timedOut(error);
    throw new ApiError(0, late ? timedOutMessage(init) : UNREACHABLE, late);
  }
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  return response;
}

export async function publicRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await (await publicFetch(path, init)).json()) as T;
}

/** Only transcribes: nothing is asked. */
export function hearQuestion(recording: Blob): Promise<AskHeard> {
  const body = new FormData();
  body.append("audio", recording, recording.type.includes("mp4") ? "question.m4a" : "question.webm");
  return publicRequest<AskHeard>("/api/ask/voice", { method: "POST", body });
}

export type SpokenPart = { audio: Blob; parts: number };

function jsonPost(body: unknown, headers: Record<string, string> = {}): RequestInit {
  return { method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify(body) };
}

async function postForAudio(path: string, body: unknown): Promise<SpokenPart> {
  const response = await publicFetch(path, jsonPost(body));
  return { audio: await response.blob(), parts: Number(response.headers.get("X-Speech-Parts") ?? 1) };
}

/** The API reads only an answer it gave, sent back as its signed export view. */
export function answerAudio(view: ExportView, part: number): Promise<SpokenPart> {
  return postForAudio("/api/speech/answer", { view, part });
}

/** The reference goes in the body, never the address. */
export function reportAudio(reference: string, kind: "receipt" | "status", part: number): Promise<SpokenPart> {
  return postForAudio("/api/speech/report", { reference, kind, part });
}

export function postJson<T>(path: string, body: unknown, headers: Record<string, string> = {}): Promise<T> {
  return publicRequest<T>(path, jsonPost(body, headers));
}

/** The API redirects to a fresh short-lived link. */
export function ledgerFileUrl(documentId: string): string {
  return `${env.apiUrl}/api/ledger/${encodeURIComponent(documentId)}/file`;
}

const reportPath = (reference: string) => `/api/reports/${encodeURIComponent(reference)}`;

export function getReportOptions(): Promise<ReportOptions> {
  return publicRequest<ReportOptions>("/api/reports/options");
}

/** A multipart report: the fields plus up to 10 "photos". */
export function fileReport(form: FormData, onProgress?: (sending: Sending) => void): Promise<ReportReceipt> {
  if (!onProgress) return publicRequest<ReportReceipt>("/api/reports", { method: "POST", body: form });
  return postWithProgress<ReportReceipt>("/api/reports", form, onProgress);
}

export function getReportStatus(reference: string): Promise<ReportStatus> {
  return publicRequest<ReportStatus>(reportPath(reference));
}

export function escalateReport(reference: string, note: string, photos: File[],
                               onProgress?: (sending: Sending) => void): Promise<ReportStatus> {
  const form = new FormData();
  form.append("note", note);
  for (const photo of photos) form.append("photos", photo);
  if (!onProgress) return publicRequest<ReportStatus>(`${reportPath(reference)}/escalate`, { method: "POST", body: form });
  return postWithProgress<ReportStatus>(`${reportPath(reference)}/escalate`, form, onProgress);
}

/** A one-time answer, authorised by the token from the receipt. */
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

export function getResponsiveness(): Promise<Responsiveness> {
  return publicRequest<Responsiveness>("/api/responsiveness");
}

export function getContacts(): Promise<ContactDirectory> {
  return publicRequest<ContactDirectory>("/api/contacts");
}

export function getRepresentatives(): Promise<Representation> {
  return publicRequest<Representation>("/api/representatives");
}

export type IssueFilters = { subMetro: string; topic: string; limit: number; offset: number };

export function getIssues({ subMetro, topic, limit, offset }: IssueFilters): Promise<IssuePage> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (subMetro) params.set("sub_metro", subMetro);
  if (topic) params.set("topic", topic);
  return publicRequest<IssuePage>(`/api/issues?${params}`);
}

export function getIssue(publicId: string): Promise<Issue> {
  return publicRequest<Issue>(`/api/issues/${encodeURIComponent(publicId)}`);
}

export function addVoice(publicId: string, deviceToken: string, name: string | null): Promise<VoiceResult> {
  return postJson<VoiceResult>(`/api/issues/${encodeURIComponent(publicId)}/voices`, { device_token: deviceToken, name });
}
