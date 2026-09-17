"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  checkDraft,
  draftLedger,
  getMyPetitions,
  getMySignature,
  getSignerNames,
  getPetition,
  getPetitionLedger,
  getPetitionOptions,
  getPetitions,
  petitionCreatorAction,
  resubmitPetition,
  signPetition,
  submitPetition,
  takeNameOffSignature,
  type CreatorAction,
  type DraftWords,
  type PetitionFilters,
  type SignChoice,
} from "@/lib/api/petitions";
import { getIssue } from "@/lib/api/public";

import type { MySignature, OwnPetition, PetitionDraft, PetitionSubmission, SignResult } from "@/lib/api/types";

const petitionKeys = {
  options: ["petition-options"] as const,
  list: (filters: PetitionFilters) => ["petitions", filters] as const,
  detail: (code: string) => ["petition", code] as const,
  ledger: (code: string) => ["petition-ledger", code] as const,
  mine: (proof: string) => ["my-petitions", proof] as const,
  signature: (code: string, proof: string) => ["my-signature", code, proof] as const,
  names: (code: string) => ["signer-names", code] as const,
};

const NAMES_PAGE = 50;

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

export function useMySignature(code: string, proof: string | null) {
  return useQuery({ queryKey: petitionKeys.signature(code, proof ?? ""), queryFn: () => getMySignature(code, proof ?? ""), enabled: proof !== null });
}

/** The signers who chose to show their name, a page at a time. */
export function useSignerNames(code: string) {
  return useInfiniteQuery({
    queryKey: petitionKeys.names(code),
    queryFn: ({ pageParam }) => getSignerNames(code, NAMES_PAGE, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const shown = pages.reduce((sum, page) => sum + page.names.length, 0);
      return shown < last.total ? shown : undefined;
    },
  });
}

/** Signing, or taking a name off a signature: then the petition, its names and this number's signature are read again. */
function useAfterSigning(code: string) {
  const queryClient = useQueryClient();
  return () => Promise.all([
    queryClient.invalidateQueries({ queryKey: petitionKeys.detail(code) }),
    queryClient.invalidateQueries({ queryKey: petitionKeys.names(code) }),
    queryClient.invalidateQueries({ queryKey: ["my-signature", code] }),
  ]);
}

export function useSignPetition(code: string) {
  const refresh = useAfterSigning(code);
  return useMutation<SignResult, Error, { choice: SignChoice; proof: string }>({
    mutationFn: ({ choice, proof }) => signPetition(code, choice, proof),
    onSuccess: () => refresh(),
  });
}

export function useTakeNameOff(code: string) {
  const refresh = useAfterSigning(code);
  return useMutation<MySignature, Error, string>({ mutationFn: (proof) => takeNameOffSignature(code, proof), onSuccess: () => refresh() });
}
