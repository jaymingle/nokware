"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import {
  getCategories,
  getLibrary,
  getReviewQueue,
  takeAction,
  uploadDocument,
} from "@/lib/api/endpoints";

import type { DocumentOut, ReviewAction } from "@/lib/api/types";

export const LIBRARY_PAGE_SIZE = 25;
const QUEUE_REFRESH_MS = 60_000; // keeps queues current as clocks run out elsewhere
const PROCESSING_REFRESH_MS = 10_000;

export const queryKeys = {
  reviewQueue: ["review-queue"] as const,
  library: (page: number) => ["library", page] as const,
  categories: ["categories"] as const,
};

/** Every list or view of documents; refreshed after any change to one. */
const DOCUMENT_QUERY_ROOTS = new Set(["review-queue", "library", "submissions", "escalations", "document"]);

function refreshDocuments(queryClient: QueryClient): Promise<void> {
  return queryClient.invalidateQueries({ predicate: (query) => DOCUMENT_QUERY_ROOTS.has(String(query.queryKey[0])) });
}

export function useReviewQueue() {
  return useQuery({ queryKey: queryKeys.reviewQueue, queryFn: getReviewQueue, refetchInterval: QUEUE_REFRESH_MS });
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

export function useCategories() {
  return useQuery({ queryKey: queryKeys.categories, queryFn: getCategories, staleTime: Infinity });
}

type ActionInput = { id: string; action: ReviewAction; note?: string };

export function useDocumentAction() {
  const queryClient = useQueryClient();
  return useMutation<DocumentOut, Error, ActionInput>({
    mutationFn: ({ id, action, note }) => takeAction(id, action, note),
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
