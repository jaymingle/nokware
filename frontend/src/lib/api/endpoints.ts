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
  PetitionDetail,
  PetitionDismissal,
  PetitionGround,
  PetitionRemovalRequest,
  PetitionReportQueue,
  PetitionResponseRequest,
  ReviewAction,
  SharedPetition,
} from "@/lib/api/types";

const documentPath = (id: string) => `/api/documents/${encodeURIComponent(id)}`;
const petitionPath = (code: string) => `/api/petitions/${encodeURIComponent(code)}`;

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

/** What readers have reported about published petitions, newest first, for a contributor to read. */
export function getPetitionReports(): Promise<PetitionReportQueue> {
  return apiRequest<PetitionReportQueue>("/api/petitions/reports");
}

/** Settles one report on a fixed reason and leaves the petition alone. Answers with the queue that is left. */
export function dismissPetitionReport(reportId: string, reason: PetitionDismissal): Promise<PetitionReportQueue> {
  return apiRequest<PetitionReportQueue>(`/api/petitions/reports/${encodeURIComponent(reportId)}/dismiss`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
}

/** Settles one report about a comment. The comment stays exactly as it is. */
export function dismissCommentReport(reportId: string, reason: PetitionDismissal): Promise<PetitionReportQueue> {
  return apiRequest<PetitionReportQueue>(`/api/petitions/comment-reports/${encodeURIComponent(reportId)}/dismiss`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
}

/** Takes one comment down on a named ground. No phone proof: a comment is not a petition anyone could have signed. */
export function removeComment(code: string, commentId: string, ground: PetitionGround): Promise<PetitionReportQueue> {
  return apiRequest<PetitionReportQueue>(`${petitionPath(code)}/comments/${encodeURIComponent(commentId)}/removal`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ground }),
  });
}

/**
 * Takes a petition down on a named ground. It needs the contributor's sign-in *and* a confirmed phone: the number
 * is how the server can tell they neither started nor signed this petition.
 */
export function removePetition(code: string, removal: PetitionRemovalRequest, proof: string): Promise<PetitionReportQueue> {
  return apiRequest<PetitionReportQueue>(`${petitionPath(code)}/removal`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Phone-Proof": proof },
    body: JSON.stringify(removal),
  });
}

/** Petitions that reached their threshold: the MCE owes each a public response within 30 days. */
export function getAwaitingResponses(): Promise<AwaitingResponse[]> {
  return apiRequest<AwaitingResponse[]>("/api/petitions/responses");
}

export function respondToPetition(code: string, response: PetitionResponseRequest): Promise<AwaitingResponse[]> {
  return apiRequest<AwaitingResponse[]>(`${petitionPath(code)}/response`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(response),
  });
}

/**
 * The MCE asks one department of the Assembly to answer this petition, by the department's team ID from
 * /api/departments. It is not a decision on the petition: the status doesn't move, and the page comes back with
 * the department on it.
 */
export function sharePetition(code: string, department: string): Promise<PetitionDetail> {
  return apiRequest<PetitionDetail>(`${petitionPath(code)}/share`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ department }),
  });
}

/** The petitions shared with the caller's own department, newest first. The server reads the department, never a page. */
export function getSharedPetitions(): Promise<SharedPetition[]> {
  return apiRequest<SharedPetition[]>("/api/petitions/shared");
}

/** The one note this department writes on a petition shared with it, published under the department's name. */
export function writeDepartmentNote(code: string, text: string): Promise<SharedPetition> {
  return apiRequest<SharedPetition>(`${petitionPath(code)}/note`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
}
