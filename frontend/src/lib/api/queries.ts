"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import {
  getCategories,
  getDepartments,
  getDocument,
  getEscalations,
  getLibrary,
  getReviewQueue,
  getSubmissions,
  resubmitDocument,
  takeAction,
  uploadDocument,
} from "@/lib/api/endpoints";

import { anyPublishingNow } from "@/lib/documents";

import type { DocumentOut, ReviewAction } from "@/lib/api/types";

export const LIBRARY_PAGE_SIZE = 25;
const QUEUE_REFRESH_MS = 60_000; // keeps queues current as clocks run out elsewhere
const PROCESSING_REFRESH_MS = 10_000;
const PUBLISHING_REFRESH_MS = 10_000; // while a clock has run out, until the deadline job publishes it

/** Refresh a queue every minute, or every 10 seconds while something is about to publish. */
function queueRefresh(documents: DocumentOut[] | undefined): number {
  return anyPublishingNow(documents, Date.now()) ? PUBLISHING_REFRESH_MS : QUEUE_REFRESH_MS;
}

export const queryKeys = {
  reviewQueue: ["review-queue"] as const,
  library: (page: number) => ["library", page] as const,
  submissions: ["submissions"] as const,
  escalations: ["escalations"] as const,
  document: (id: string) => ["document", id] as const,
  categories: ["categories"] as const,
  departments: ["departments"] as const,
};

/** Every list or view of documents; refreshed after any change to one. */
const DOCUMENT_QUERY_ROOTS = new Set(["review-queue", "library", "submissions", "escalations", "document"]);

function refreshDocuments(queryClient: QueryClient): Promise<void> {
  return queryClient.invalidateQueries({ predicate: (query) => DOCUMENT_QUERY_ROOTS.has(String(query.queryKey[0])) });
}

/** Reloads every document view, e.g. after an action failed because a document changed elsewhere. */
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
    // Poll while any document on the page is still being indexed for Ask.
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

/** One document with its audit trail, fetched only once it's wanted. */
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
