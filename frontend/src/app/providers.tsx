"use client";

import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ApiError } from "@/lib/api/client";

const MAX_RETRIES = 2;

function shouldRetry(failureCount: number, error: Error): boolean {
  // Retry only when the service may recover (unreachable or a 5xx), never a refusal.
  const transient = !(error instanceof ApiError) || error.status === 0 || error.status >= 500;
  return transient && failureCount < MAX_RETRIES;
}

let browserQueryClient: QueryClient | undefined;

function makeQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: shouldRetry } } });
}

function getQueryClient(): QueryClient {
  // Keep server renders isolated and one cache for the life of the browser tab.
  if (typeof window === "undefined") return makeQueryClient();
  browserQueryClient ??= makeQueryClient();
  return browserQueryClient;
}

export function Providers({ children }: { children: ReactNode }) {
  return <QueryClientProvider client={getQueryClient()}>{children}</QueryClientProvider>;
}
