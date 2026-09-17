"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addVoice,
  escalateReport,
  getContacts,
  getIssues,
  fileReport,
  getDashboard,
  getPublishingRecord,
  getReportOptions,
  getReportStatus,
  getRepresentatives,
  getResponsiveness,
  setReportPreferences,
  type IssueFilters,
} from "@/lib/api/public";

import type { PreferencesResult, ReportPreferences, ReportReceipt, ReportStatus, VoiceResult } from "@/lib/api/types";

const DASHBOARD_STALE_MS = 60_000; // the API recomputes the figures at most once a minute

const publicKeys = {
  reportOptions: ["report-options"] as const,
  reportStatus: (reference: string) => ["report-status", reference] as const,
  dashboard: ["dashboard"] as const,
  publishingRecord: ["publishing-record"] as const,
  responsiveness: ["responsiveness"] as const,
  contacts: ["contacts"] as const,
  representatives: ["representatives"] as const,
  issues: (filters: IssueFilters) => ["issues", filters] as const,
};

export function useReportOptions() {
  return useQuery({ queryKey: publicKeys.reportOptions, queryFn: getReportOptions, staleTime: Infinity });
}

export function useFileReport() {
  return useMutation<ReportReceipt, Error, FormData>({ mutationFn: fileReport });
}

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

/** For a citizen clearing the page on a shared device. */
export function useForgetStatus(): (reference: string) => void {
  const queryClient = useQueryClient();
  return (reference) => queryClient.removeQueries({ queryKey: publicKeys.reportStatus(reference) });
}

export function usePublishingRecord() {
  return useQuery({ queryKey: publicKeys.publishingRecord, queryFn: getPublishingRecord, staleTime: 10 * 60_000 });
}

export function useResponsiveness() {
  return useQuery({ queryKey: publicKeys.responsiveness, queryFn: getResponsiveness, staleTime: DASHBOARD_STALE_MS });
}

export function useContacts() {
  return useQuery({ queryKey: publicKeys.contacts, queryFn: getContacts, staleTime: Infinity });
}

export function useRepresentatives() {
  return useQuery({ queryKey: publicKeys.representatives, queryFn: getRepresentatives, staleTime: Infinity });
}

export function useIssues(filters: IssueFilters) {
  return useQuery({ queryKey: publicKeys.issues(filters), queryFn: () => getIssues(filters), placeholderData: (previous) => previous });
}

type VoiceInput = { publicId: string; deviceToken: string; name: string | null };

export function useAddVoice() {
  const queryClient = useQueryClient();
  return useMutation<VoiceResult, Error, VoiceInput>({
    mutationFn: ({ publicId, deviceToken, name }) => addVoice(publicId, deviceToken, name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["issues"] }),
  });
}
