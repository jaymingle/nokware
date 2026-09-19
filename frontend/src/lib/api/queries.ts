"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import {
  dismissPetitionReport,
  getAwaitingResponses,
  getCase,
  getPetitionReports,
  openSharedLocation,
  removePetition,
  respondToPetition,
  getCaseOversight,
  getCaseQueue,
  getCategories,
  getDepartments,
  getDocument,
  getEscalations,
  getLibrary,
  getReviewQueue,
  getSharedPetitions,
  getSubmissions,
  resubmitDocument,
  sharePetition,
  takeAction,
  takeCaseAction,
  uploadDocument,
  writeDepartmentNote,
  type CaseActionBody,
} from "@/lib/api/endpoints";
import { anyPublishingNow } from "@/lib/documents";

import type {
  AwaitingResponse,
  CaseAction,
  CaseDetail,
  DocumentOut,
  PetitionDetail,
  PetitionDismissal,
  PetitionRemovalRequest,
  PetitionReportQueue,
  PetitionResponseRequest,
  ReviewAction,
  SharedLocationView,
  SharedPetition,
} from "@/lib/api/types";

export const LIBRARY_PAGE_SIZE = 25;
const QUEUE_REFRESH_MS = 60_000; // keeps queues current as clocks run out elsewhere
const PROCESSING_REFRESH_MS = 10_000;
const PUBLISHING_REFRESH_MS = 10_000; // while a clock has run out, until the deadline job publishes it

function queueRefresh(documents: DocumentOut[] | undefined): number {
  return anyPublishingNow(documents, Date.now()) ? PUBLISHING_REFRESH_MS : QUEUE_REFRESH_MS;
}

const queryKeys = {
  reviewQueue: ["review-queue"] as const,
  library: (page: number) => ["library", page] as const,
  submissions: ["submissions"] as const,
  escalations: ["escalations"] as const,
  document: (id: string) => ["document", id] as const,
  caseQueue: ["cases", "queue"] as const,
  caseOversight: ["cases", "oversight"] as const,
  case: (id: string) => ["cases", "detail", id] as const,
  categories: ["categories"] as const,
  departments: ["departments"] as const,
  petitionReports: ["petition-reports"] as const,
  awaitingResponses: ["petition-responses"] as const,
  sharedPetitions: ["petitions-shared"] as const,
};

/** Every list or view of documents; refreshed after any change to one. */
const DOCUMENT_QUERY_ROOTS = new Set(["review-queue", "library", "submissions", "escalations", "document"]);

function refreshDocuments(queryClient: QueryClient): Promise<void> {
  return queryClient.invalidateQueries({ predicate: (query) => DOCUMENT_QUERY_ROOTS.has(String(query.queryKey[0])) });
}

/** For when an action failed because the document changed elsewhere. */
export function useRefreshDocuments(): () => Promise<void> {
  const queryClient = useQueryClient();
  return () => refreshDocuments(queryClient);
}

export function useReviewQueue() {
  return useQuery({
    queryKey: queryKeys.reviewQueue,
    queryFn: getReviewQueue,
    refetchInterval: (query) => queueRefresh(query.state.data),
  });
}

export function useLibrary(page: number) {
  return useQuery({
    queryKey: queryKeys.library(page),
    queryFn: () => getLibrary(LIBRARY_PAGE_SIZE, page * LIBRARY_PAGE_SIZE),
    placeholderData: keepPreviousData,
    refetchInterval: (query) =>
      query.state.data?.documents.some((doc) => doc.ingestion === "processing") ? PROCESSING_REFRESH_MS : false,
  });
}

export function useSubmissions() {
  return useQuery({
    queryKey: queryKeys.submissions,
    queryFn: getSubmissions,
    refetchInterval: (query) => queueRefresh(query.state.data),
  });
}

export function useEscalations() {
  return useQuery({
    queryKey: queryKeys.escalations,
    queryFn: getEscalations,
    refetchInterval: (query) => queueRefresh(query.state.data),
  });
}

export function useDocumentDetail(id: string, enabled: boolean) {
  return useQuery({ queryKey: queryKeys.document(id), queryFn: () => getDocument(id), enabled });
}

export function useCategories() {
  return useQuery({ queryKey: queryKeys.categories, queryFn: getCategories, staleTime: Infinity });
}

export function useDepartments() {
  return useQuery({ queryKey: queryKeys.departments, queryFn: getDepartments, staleTime: Infinity });
}

type ActionInput = { id: string; action: ReviewAction; note?: string };

export function useDocumentAction() {
  const queryClient = useQueryClient();
  return useMutation<DocumentOut, Error, ActionInput>({
    mutationFn: ({ id, action, note }) => takeAction(id, action, note),
    onSuccess: () => refreshDocuments(queryClient),
  });
}

type ResubmitInput = { id: string; form: FormData };

export function useResubmit() {
  const queryClient = useQueryClient();
  return useMutation<DocumentOut, Error, ResubmitInput>({
    mutationFn: ({ id, form }) => resubmitDocument(id, form),
    onSuccess: () => refreshDocuments(queryClient),
  });
}

export function useUploadDocument() {
  const queryClient = useQueryClient();
  return useMutation<DocumentOut, Error, FormData>({
    mutationFn: uploadDocument,
    onSuccess: () => refreshDocuments(queryClient),
  });
}

const CASES_REFRESH_MS = 60_000; // new reports arrive at any time

export function useCaseQueue() {
  return useQuery({ queryKey: queryKeys.caseQueue, queryFn: getCaseQueue, refetchInterval: CASES_REFRESH_MS });
}

export function useCaseOversight() {
  return useQuery({ queryKey: queryKeys.caseOversight, queryFn: getCaseOversight, refetchInterval: CASES_REFRESH_MS });
}

export function useCase(id: string | null) {
  return useQuery({ queryKey: queryKeys.case(id ?? ""), queryFn: () => getCase(id ?? ""), enabled: id !== null });
}

export type CaseActionInput = { id: string; action: CaseAction; body?: CaseActionBody };

export function useCaseAction() {
  const queryClient = useQueryClient();
  return useMutation<CaseDetail, Error, CaseActionInput>({
    mutationFn: ({ id, action, body }) => takeCaseAction(id, action, body),
    onSuccess: (detail) => {
      queryClient.setQueryData(queryKeys.case(detail.case_id), detail);
      return queryClient.invalidateQueries({ queryKey: ["cases"] });
    },
  });
}

/** Opening a shared location is an act, not a read: it goes to the audit trail, so the case is refetched after. */
export function useOpenLocation() {
  const queryClient = useQueryClient();
  return useMutation<SharedLocationView, Error, string>({
    mutationFn: openSharedLocation,
    onSuccess: (_, id) => queryClient.invalidateQueries({ queryKey: queryKeys.case(id) }),
  });
}

const PETITIONS_REFRESH_MS = 60_000; // petitions are published, signed and reported at any time

export function useAwaitingResponses() {
  return useQuery({ queryKey: queryKeys.awaitingResponses, queryFn: getAwaitingResponses, refetchInterval: PETITIONS_REFRESH_MS });
}

/** Every public view of a petition, refreshed after a response or a removal changes one. */
function refreshPetitions(queryClient: QueryClient): Promise<void> {
  return queryClient.invalidateQueries({ predicate: (query) => PETITION_QUERY_ROOTS.has(String(query.queryKey[0])) });
}

const PETITION_QUERY_ROOTS = new Set(["petitions", "petition", "petition-responses", "petitions-shared"]);

export function useRespondToPetition() {
  const queryClient = useQueryClient();
  return useMutation<AwaitingResponse[], Error, { code: string; response: PetitionResponseRequest }>({
    mutationFn: ({ code, response }) => respondToPetition(code, response),
    onSuccess: (waiting) => {
      queryClient.setQueryData(queryKeys.awaitingResponses, waiting);
      return refreshPetitions(queryClient);
    },
  });
}

/** Asking a department to answer is not a decision on the petition, so nothing here waits on its status. */
export function useSharePetition() {
  const queryClient = useQueryClient();
  return useMutation<PetitionDetail, Error, { code: string; department: string }>({
    mutationFn: ({ code, department }) => sharePetition(code, department),
    onSuccess: () => refreshPetitions(queryClient),
  });
}

/** What the caller's own department has been asked to answer. The server reads the department from the session. */
export function useSharedPetitions() {
  return useQuery({ queryKey: queryKeys.sharedPetitions, queryFn: getSharedPetitions, refetchInterval: PETITIONS_REFRESH_MS });
}

export function useWriteDepartmentNote() {
  const queryClient = useQueryClient();
  return useMutation<SharedPetition, Error, { code: string; text: string }>({
    mutationFn: ({ code, text }) => writeDepartmentNote(code, text),
    onSuccess: () => refreshPetitions(queryClient),
  });
}

export function usePetitionReports() {
  return useQuery({ queryKey: queryKeys.petitionReports, queryFn: getPetitionReports, refetchInterval: PETITIONS_REFRESH_MS });
}

/** Both a dismissal and a removal answer with the queue that is left, so it replaces what is on screen. */
function useSettleReport<TInput>(settle: (input: TInput) => Promise<PetitionReportQueue>, alsoPetitions: boolean) {
  const queryClient = useQueryClient();
  return useMutation<PetitionReportQueue, Error, TInput>({
    mutationFn: settle,
    onSuccess: (queue) => {
      queryClient.setQueryData(queryKeys.petitionReports, queue);
      return alsoPetitions ? refreshPetitions(queryClient) : undefined;
    },
  });
}

export function useDismissReport() {
  return useSettleReport<{ reportId: string; reason: PetitionDismissal }>(
    ({ reportId, reason }) => dismissPetitionReport(reportId, reason), false);
}

export function useRemovePetition() {
  return useSettleReport<{ code: string; removal: PetitionRemovalRequest; proof: string }>(
    ({ code, removal, proof }) => removePetition(code, removal, proof), true);
}
