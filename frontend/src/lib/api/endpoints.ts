import { apiRequest } from "@/lib/api/client";

import type {
  AwaitingResponse,
  CaseAction,
  CaseDetail,
  CaseOversight,
  CaseSummary,
  SharedLocationView,
  DocumentDetail,
  DocumentOut,
  DocumentPage,
  FileLink,
  Me,
  Option,
  PetitionDecision,
  ReviewAction,
  ReviewQueue,
} from "@/lib/api/types";

const documentPath = (id: string) => `/api/documents/${encodeURIComponent(id)}`;

export function getMe(): Promise<Me> {
  return apiRequest<Me>("/api/me");
}

export function getCategories(): Promise<Option[]> {
  return apiRequest<Option[]>("/api/categories");
}

export function getDepartments(): Promise<Option[]> {
  return apiRequest<Option[]>("/api/departments");
}

export function getReviewQueue(): Promise<DocumentOut[]> {
  return apiRequest<DocumentOut[]>("/api/review-queue");
}

export function getSubmissions(): Promise<DocumentOut[]> {
  return apiRequest<DocumentOut[]>("/api/documents/mine");
}

export function getEscalations(): Promise<DocumentOut[]> {
  return apiRequest<DocumentOut[]>("/api/escalations");
}

export function getLibrary(limit: number, offset: number): Promise<DocumentPage> {
  return apiRequest<DocumentPage>(`/api/documents/library?limit=${limit}&offset=${offset}`);
}

export function getDocument(id: string): Promise<DocumentDetail> {
  return apiRequest<DocumentDetail>(documentPath(id));
}

export function getFileLink(id: string): Promise<FileLink> {
  return apiRequest<FileLink>(`${documentPath(id)}/file`);
}

export function takeAction(id: string, action: ReviewAction, note?: string): Promise<DocumentOut> {
  return apiRequest<DocumentOut>(`${documentPath(id)}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ note: note ?? null }),
  });
}

/** A revised PDF ("file") and optional "note", sent after a dispute. */
export function resubmitDocument(id: string, form: FormData): Promise<DocumentOut> {
  return apiRequest<DocumentOut>(`${documentPath(id)}/resubmit`, { method: "POST", body: form });
}

/** A multipart upload: the PDF as "file" plus the form fields. */
export function uploadDocument(form: FormData): Promise<DocumentOut> {
  return apiRequest<DocumentOut>("/api/documents", { method: "POST", body: form });
}

const casePath = (id: string) => `/api/cases/${encodeURIComponent(id)}`;

export function getCaseQueue(): Promise<{ cases: CaseSummary[] }> {
  return apiRequest<{ cases: CaseSummary[] }>("/api/cases/queue");
}

export function getCaseOversight(): Promise<CaseOversight> {
  return apiRequest<CaseOversight>("/api/cases/oversight");
}

export function getCase(id: string): Promise<CaseDetail> {
  return apiRequest<CaseDetail>(casePath(id));
}

/** A shared precise location, opened on purpose: the view is recorded and the citizen is told. */
export function openSharedLocation(id: string): Promise<SharedLocationView> {
  return apiRequest<SharedLocationView>(`${casePath(id)}/location`);
}

/** A note for resolve / reopen / confirm-resolution; from, to and reason for reassign. */
export type CaseActionBody = { note?: string; from_recipient?: string; to_recipient?: string; reason?: string };

export function takeCaseAction(id: string, action: CaseAction, body?: CaseActionBody): Promise<CaseDetail> {
  return apiRequest<CaseDetail>(`${casePath(id)}/${action}`, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
}

/** Petitions waiting for the MCE, the one closest to publishing automatically first. */
export function getPetitionReview(): Promise<ReviewQueue> {
  return apiRequest<ReviewQueue>("/api/petitions/review");
}

/** Publish a petition, or refuse it for one of the fixed reasons; the queue as it then stands. */
export function decidePetition(code: string, decision: PetitionDecision): Promise<ReviewQueue> {
  return apiRequest<ReviewQueue>(`/api/petitions/${encodeURIComponent(code)}/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(decision),
  });
}

/** Petitions that reached their threshold: the MCE owes each a public response within 30 days. */
export function getAwaitingResponses(): Promise<AwaitingResponse[]> {
  return apiRequest<AwaitingResponse[]>("/api/petitions/responses");
}
