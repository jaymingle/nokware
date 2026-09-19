"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addPetitionComment,
  checkDraft,
  draftLedger,
  editPetition,
  getMyPetitions,
  getMySignature,
  getPetitionComments,
  getSignerNames,
  getPetition,
  getPetitionLedger,
  getPetitionOptions,
  getPetitions,
  petitionCreatorAction,
  replyToResponse,
  reportPetition,
  reportPetitionComment,
  signPetition,
  submitPetition,
  takeNameOffSignature,
  type CreatorAction,
  type DraftWords,
  type NewComment,
  type NewPetition,
  type PetitionEditSend,
  type PetitionFilters,
  type SignChoice,
} from "@/lib/api/petitions";
import { getIssue } from "@/lib/api/public";

import type {
  MySignature,
  OwnPetition,
  PetitionComment,
  PetitionCommentReportRequest,
  PetitionDetail,
  PetitionReportFiled,
  PetitionReportRequest,
  SignResult,
} from "@/lib/api/types";
import type { Sending } from "@/lib/api/upload";

const petitionKeys = {
  options: ["petition-options"] as const,
  list: (filters: PetitionFilters) => ["petitions", filters] as const,
  detail: (code: string) => ["petition", code] as const,
  ledger: (code: string) => ["petition-ledger", code] as const,
  mine: (proof: string) => ["my-petitions", proof] as const,
  signature: (code: string, proof: string) => ["my-signature", code, proof] as const,
  names: (code: string) => ["signer-names", code] as const,
  comments: (code: string) => ["petition-comments", code] as const,
};

const NAMES_PAGE = 50;
const COMMENTS_PAGE = 20;

export function usePetitionOptions() {
  return useQuery({ queryKey: petitionKeys.options, queryFn: getPetitionOptions, staleTime: Infinity });
}

export function usePetitions(filters: PetitionFilters) {
  return useQuery({ queryKey: petitionKeys.list(filters), queryFn: () => getPetitions(filters) });
}

export function usePetition(code: string) {
  return useQuery({ queryKey: petitionKeys.detail(code), queryFn: () => getPetition(code) });
}

/** The Ledger search is slow and changes rarely. The shared policy decides retries: `retry: 1` tried a second
 * time even after a request had waited its whole deadline, and the section spun for a minute saying "Searching". */
export function usePetitionLedger(code: string) {
  return useQuery({ queryKey: petitionKeys.ledger(code), queryFn: () => getPetitionLedger(code), staleTime: Infinity });
}

/** Not retried: a closed issue stays closed. */
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

/** The photos are the wait on a mobile connection, so the caller is told how far they have gone. */
export function useSubmitPetition(onProgress: (sending: Sending) => void) {
  return useMutation<OwnPetition, Error, { petition: NewPetition; proof: string }>({
    mutationFn: ({ petition, proof }) => submitPetition(petition, proof, onProgress),
  });
}

export function useEditPetition(onProgress: (sending: Sending) => void) {
  const queryClient = useQueryClient();
  return useMutation<OwnPetition, Error, { code: string; edit: PetitionEditSend; proof: string }>({
    mutationFn: ({ code, edit, proof }) => editPetition(code, edit, proof, onProgress),
    onSuccess: (_petition, { code }) => Promise.all([
      queryClient.invalidateQueries({ queryKey: ["my-petitions"] }),
      queryClient.invalidateQueries({ queryKey: petitionKeys.detail(code) }),
    ]),
  });
}

export function useChangePetition() {
  const queryClient = useQueryClient();
  return useMutation<OwnPetition, Error, { code: string; proof: string; action: CreatorAction }>({
    mutationFn: ({ code, action, proof }) => petitionCreatorAction(code, action, proof),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["my-petitions"] }),
  });
}

/** No sign-in, and nothing on the page changes: the petition stays up while a contributor reads the report. */
export function useReportPetition(code: string) {
  return useMutation<PetitionReportFiled, Error, PetitionReportRequest>({
    mutationFn: (report) => reportPetition(code, report),
  });
}

export function useMySignature(code: string, proof: string | null) {
  return useQuery({ queryKey: petitionKeys.signature(code, proof ?? ""), queryFn: () => getMySignature(code, proof ?? ""), enabled: proof !== null });
}

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

export function usePetitionComments(code: string) {
  return useInfiniteQuery({
    queryKey: petitionKeys.comments(code),
    queryFn: ({ pageParam }) => getPetitionComments(code, COMMENTS_PAGE, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => {
      const shown = pages.reduce((sum, page) => sum + page.comments.length, 0);
      return shown < last.total ? shown : undefined;
    },
  });
}

/** The petition's own count is on its page too, so both are read again once a comment is published. */
export function useAddComment(code: string) {
  const queryClient = useQueryClient();
  return useMutation<PetitionComment, Error, { comment: NewComment; proof: string }>({
    mutationFn: ({ comment, proof }) => addPetitionComment(code, comment, proof),
    onSuccess: () => Promise.all([
      queryClient.invalidateQueries({ queryKey: petitionKeys.comments(code) }),
      queryClient.invalidateQueries({ queryKey: petitionKeys.detail(code) }),
    ]),
  });
}

/** No sign-in, and nothing on the page changes: the comment stays up while a contributor reads the report. */
export function useReportComment(code: string, commentId: string) {
  return useMutation<PetitionReportFiled, Error, PetitionCommentReportRequest>({
    mutationFn: (report) => reportPetitionComment(code, commentId, report),
  });
}

/** The API answers with the petition as it now reads, so the reply stands on the page without another request. */
export function useReplyToResponse(code: string) {
  const queryClient = useQueryClient();
  return useMutation<PetitionDetail, Error, { text: string; proof: string }>({
    mutationFn: ({ text, proof }) => replyToResponse(code, text, proof),
    onSuccess: (petition) => queryClient.setQueryData(petitionKeys.detail(code), petition),
  });
}
