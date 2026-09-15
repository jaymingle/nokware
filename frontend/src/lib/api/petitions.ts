// Petitions and phone confirmation: public routes, no sign-in. A creator's own petitions need the proof a
// confirmed phone gives this page, sent as X-Phone-Proof.
import { postJson, publicRequest } from "@/lib/api/public";

import type {
  LedgerMatch,
  MyPetitions,
  OwnPetition,
  PetitionDetail,
  PetitionDraft,
  PetitionOptions,
  PetitionPage,
  PetitionSubmission,
  PhoneChallenge,
  PhoneChallengeStatus,
  ScreenResult,
  SmsCodeSent,
} from "@/lib/api/types";

export type PetitionGroup = "open" | "closed";
export type PetitionFilters = { group: PetitionGroup; topic: string; limit: number; offset: number };

const petitionPath = (code: string) => `/api/petitions/${encodeURIComponent(code)}`;
const proofHeader = (proof: string) => ({ "X-Phone-Proof": proof });

export function getPetitionOptions(): Promise<PetitionOptions> {
  return publicRequest<PetitionOptions>("/api/petitions/options");
}

export function getPetitions({ group, topic, limit, offset }: PetitionFilters): Promise<PetitionPage> {
  const params = new URLSearchParams({ group, limit: String(limit), offset: String(offset) });
  if (topic) params.set("topic", topic);
  return publicRequest<PetitionPage>(`/api/petitions?${params}`);
}

export function getPetition(code: string): Promise<PetitionDetail> {
  return publicRequest<PetitionDetail>(petitionPath(code));
}

/** What the Ledger holds on a published petition's subject. */
export function getPetitionLedger(code: string): Promise<LedgerMatch[]> {
  return publicRequest<LedgerMatch[]>(`${petitionPath(code)}/ledger`);
}

export type DraftWords = { title: string; body: string };

export function checkDraft(words: DraftWords): Promise<ScreenResult> {
  return postJson<ScreenResult>("/api/petitions/check", words);
}

export function draftLedger(words: DraftWords & { topic: string }): Promise<LedgerMatch[]> {
  return postJson<LedgerMatch[]>("/api/petitions/ledger", words);
}

export function submitPetition(submission: PetitionSubmission, proof: string): Promise<OwnPetition> {
  return postJson<OwnPetition>("/api/petitions", submission, proofHeader(proof));
}

export function getMyPetitions(proof: string): Promise<MyPetitions> {
  return publicRequest<MyPetitions>("/api/petitions/mine", { headers: proofHeader(proof) });
}

export function resubmitPetition(code: string, draft: PetitionDraft, proof: string): Promise<OwnPetition> {
  return postJson<OwnPetition>(`${petitionPath(code)}/resubmit`, draft, proofHeader(proof));
}

export type CreatorAction = "withdraw" | "anonymous";

export function petitionCreatorAction(code: string, action: CreatorAction, proof: string): Promise<OwnPetition> {
  return postJson<OwnPetition>(`${petitionPath(code)}/${action}`, {}, proofHeader(proof));
}

export function newPhoneChallenge(): Promise<PhoneChallenge> {
  return postJson<PhoneChallenge>("/api/phone/challenges", {});
}

export function phoneChallengeStatus(challenge: string): Promise<PhoneChallengeStatus> {
  return postJson<PhoneChallengeStatus>("/api/phone/challenges/status", { challenge });
}

export function sendSmsCode(challenge: string, phone: string): Promise<SmsCodeSent> {
  return postJson<SmsCodeSent>("/api/phone/challenges/sms", { challenge, phone });
}

export function confirmSmsCode(challenge: string, code: string): Promise<PhoneChallengeStatus> {
  return postJson<PhoneChallengeStatus>("/api/phone/challenges/sms/confirm", { challenge, code });
}
