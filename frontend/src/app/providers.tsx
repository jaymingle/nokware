"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { shouldRetry } from "@/lib/api/errors";

import type { ReactNode } from "react";

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
