"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  escalateReport,
  fileReport,
  getDashboard,
  getReportOptions,
  getReportStatus,
  setReportPreferences,
} from "@/lib/api/public";

import type { PreferencesResult, ReportPreferences, ReportReceipt, ReportStatus } from "@/lib/api/types";

const DASHBOARD_STALE_MS = 60_000; // the API recomputes the figures at most once a minute

export const publicKeys = {
  reportOptions: ["report-options"] as const,
  reportStatus: (reference: string) => ["report-status", reference] as const,
  dashboard: ["dashboard"] as const,
};

export function useReportOptions() {
  return useQuery({ queryKey: publicKeys.reportOptions, queryFn: getReportOptions, staleTime: Infinity });
}

export function useFileReport() {
  return useMutation<ReportReceipt, Error, FormData>({ mutationFn: fileReport });
}

/** A case's status once a reference has been entered; nothing is fetched before. */
export function useReportStatus(reference: string | null) {
  return useQuery({
    queryKey: publicKeys.reportStatus(reference ?? ""),
    queryFn: () => getReportStatus(reference ?? ""),
    enabled: reference !== null,
  });
}

type EscalateInput = { reference: string; note: string };

export function useEscalateReport() {
  const queryClient = useQueryClient();
  return useMutation<ReportStatus, Error, EscalateInput>({
    mutationFn: ({ reference, note }) => escalateReport(reference, note),
    onSuccess: (status, { reference }) => queryClient.setQueryData(publicKeys.reportStatus(reference), status),
  });
}

type PreferencesInput = { reference: string; token: string; choice: ReportPreferences };

export function useReportPreferences() {
  return useMutation<PreferencesResult, Error, PreferencesInput>({
    mutationFn: ({ reference, token, choice }) => setReportPreferences(reference, token, choice),
  });
}

export function useDashboard() {
  return useQuery({ queryKey: publicKeys.dashboard, queryFn: getDashboard, staleTime: DASHBOARD_STALE_MS });
}

/** Drops a looked-up status from memory, for a citizen clearing the page on a shared device. */
export function useForgetStatus(): (reference: string) => void {
  const queryClient = useQueryClient();
  return (reference) => queryClient.removeQueries({ queryKey: publicKeys.reportStatus(reference) });
}
