"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  checkDraft,
  draftLedger,
  getMyPetitions,
  getPetition,
  getPetitionLedger,
  getPetitionOptions,
  getPetitions,
  petitionCreatorAction,
  resubmitPetition,
  submitPetition,
  type CreatorAction,
  type DraftWords,
  type PetitionFilters,
} from "@/lib/api/petitions";
import { getIssue } from "@/lib/api/public";

import type { OwnPetition, PetitionDraft, PetitionSubmission } from "@/lib/api/types";

export const petitionKeys = {
  options: ["petition-options"] as const,
  list: (filters: PetitionFilters) => ["petitions", filters] as const,
  detail: (code: string) => ["petition", code] as const,
  ledger: (code: string) => ["petition-ledger", code] as const,
  mine: (proof: string) => ["my-petitions", proof] as const,
};

export function usePetitionOptions() {
  return useQuery({ queryKey: petitionKeys.options, queryFn: getPetitionOptions, staleTime: Infinity });
}

export function usePetitions(filters: PetitionFilters) {
  return useQuery({ queryKey: petitionKeys.list(filters), queryFn: () => getPetitions(filters) });
}

export function usePetition(code: string) {
  return useQuery({ queryKey: petitionKeys.detail(code), queryFn: () => getPetition(code) });
}

/** The Ledger search is slow and changes rarely: kept for the page's life, and tried once more at most if it fails. */
export function usePetitionLedger(code: string) {
  return useQuery({ queryKey: petitionKeys.ledger(code), queryFn: () => getPetitionLedger(code), staleTime: Infinity, retry: 1 });
}

/** The open issue a petition links to, to say what it is; not retried, since a closed issue stays closed. */
export function useLinkedIssue(publicId: string | null) {
  return useQuery({ queryKey: ["issue", publicId], queryFn: () => getIssue(publicId ?? ""), enabled: publicId !== null, retry: false });
}

export function useMyPetitions(proof: string | null) {
  return useQuery({ queryKey: petitionKeys.mine(proof ?? ""), queryFn: () => getMyPetitions(proof ?? ""), enabled: proof !== null });
}

export function useCheckDraft() {
  return useMutation({ mutationFn: (words: DraftWords) => checkDraft(words) });
}

export function useDraftLedger() {
  return useMutation({ mutationFn: (words: DraftWords & { topic: string }) => draftLedger(words) });
}

export function useSubmitPetition() {
  return useMutation<OwnPetition, Error, { submission: PetitionSubmission; proof: string }>({
    mutationFn: ({ submission, proof }) => submitPetition(submission, proof),
  });
}

type ChangeInput = { code: string; proof: string } & ({ action: CreatorAction } | { draft: PetitionDraft });

/** Withdraw, take the name off, or send a refused petition back: then the creator's list is read again. */
export function useChangePetition() {
  const queryClient = useQueryClient();
  return useMutation<OwnPetition, Error, ChangeInput>({
    mutationFn: (input) =>
      "draft" in input ? resubmitPetition(input.code, input.draft, input.proof) : petitionCreatorAction(input.code, input.action, input.proof),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["my-petitions"] }),
  });
}
