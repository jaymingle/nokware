import { apiRequest } from "@/lib/api/client";

import type {
  DocumentDetail,
  DocumentOut,
  DocumentPage,
  FileLink,
  Me,
  Option,
  ReviewAction,
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
