// Petitions and phone confirmation: public routes, no sign-in. A creator's own petitions need the proof a
// confirmed phone gives this page, sent as X-Phone-Proof.
import { postJson, publicRequest } from "@/lib/api/public";
import { postWithProgress, type Sending } from "@/lib/api/upload";

import type {
  LedgerMatch,
  MyPetitions,
  MySignature,
  NamedSignatures,
  OwnPetition,
  PetitionComment,
  PetitionCommentPage,
  PetitionCommentReportRequest,
  PetitionDetail,
  PetitionOptions,
  PetitionOrTombstone,
  PetitionPage,
  PetitionReportFiled,
  PetitionReportRequest,
  PhoneChallenge,
  PhoneChallengeStatus,
  ScreenResult,
  SignResult,
  SmsCodeSent,
} from "@/lib/api/types";

/** The groups the API lists under. "removed" lists tombstones, not petitions, and no topic narrows it. */
export type PetitionGroup = "open" | "awaiting" | "responded" | "closed" | "removed";
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

/** Either the petition or, where one was removed, its tombstone. Discriminate on `state`. */
export function getPetition(code: string): Promise<PetitionOrTombstone> {
  return publicRequest<PetitionOrTombstone>(petitionPath(code));
}

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

/** The words a petition is made of. An edit sends them all again, so both calls take the same shape. */
export type PetitionWords = {
  title: string;
  body: string;
  topic: string;
  scope: "metro" | "area";
  ward: string | null;
  issue: string | null;
  documents: string[];
};

/**
 * The words and the photos in one request. The API takes both as a form — a petition has no number until this
 * call gives it one, so there is nowhere to upload a photo to beforehand.
 */
function petitionForm(words: PetitionWords, images: File[]): FormData {
  const form = new FormData();
  form.append("title", words.title);
  form.append("body", words.body);
  form.append("topic", words.topic);
  form.append("scope", words.scope);
  if (words.ward) form.append("ward", words.ward);
  if (words.issue) form.append("issue", words.issue);
  for (const id of words.documents) form.append("documents", id);
  for (const image of images) form.append("images", image, image.name);
  return form;
}

export type NewPetition = { words: PetitionWords; images: File[]; showName: boolean; name: string | null };

export function submitPetition(petition: NewPetition, proof: string, onProgress: (sending: Sending) => void): Promise<OwnPetition> {
  const form = petitionForm(petition.words, petition.images);
  form.append("show_name", String(petition.showName));
  if (petition.name) form.append("name", petition.name);
  return postWithProgress<OwnPetition>("/api/petitions", form, onProgress, proofHeader(proof));
}

/** `keepImages` names the images of the version before that this one keeps; anything left out goes. */
export type PetitionEditSend = { words: PetitionWords; images: File[]; keepImages: string[] };

export function editPetition(code: string, edit: PetitionEditSend, proof: string,
                             onProgress: (sending: Sending) => void): Promise<OwnPetition> {
  const form = petitionForm(edit.words, edit.images);
  for (const id of edit.keepImages) form.append("keep_images", id);
  return postWithProgress<OwnPetition>(`${petitionPath(code)}/edit`, form, onProgress, proofHeader(proof));
}

export function getMyPetitions(proof: string): Promise<MyPetitions> {
  return publicRequest<MyPetitions>("/api/petitions/mine", { headers: proofHeader(proof) });
}

/** Anyone, without signing in: the petition stays up while a contributor reads it. */
export function reportPetition(code: string, report: PetitionReportRequest): Promise<PetitionReportFiled> {
  return postJson<PetitionReportFiled>(`${petitionPath(code)}/report`, report);
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

export type SignChoice = { show_name: boolean; name: string | null };

export function signPetition(code: string, choice: SignChoice, proof: string): Promise<SignResult> {
  return postJson<SignResult>(`${petitionPath(code)}/signatures`, choice, proofHeader(proof));
}

export function getMySignature(code: string, proof: string): Promise<MySignature> {
  return publicRequest<MySignature>(`${petitionPath(code)}/signature`, { headers: proofHeader(proof) });
}

export function takeNameOffSignature(code: string, proof: string): Promise<MySignature> {
  return postJson<MySignature>(`${petitionPath(code)}/signature/anonymous`, {}, proofHeader(proof));
}

/** Newest first. */
export function getSignerNames(code: string, limit: number, offset: number): Promise<NamedSignatures> {
  return publicRequest<NamedSignatures>(`${petitionPath(code)}/names?limit=${limit}&offset=${offset}`);
}

/** Newest first. A removed petition has none to give: they went down with it, and are back when it is. */
export function getPetitionComments(code: string, limit: number, offset: number): Promise<PetitionCommentPage> {
  return publicRequest<PetitionCommentPage>(`${petitionPath(code)}/comments?limit=${limit}&offset=${offset}`);
}

/** `name` empty leaves the comment standing as "Resident". */
export type NewComment = { text: string; name: string | null };

/** The same confirmed number a signature is given with, and nothing more stored with it than with one. */
export function addPetitionComment(code: string, comment: NewComment, proof: string): Promise<PetitionComment> {
  return postJson<PetitionComment>(`${petitionPath(code)}/comments`, comment, proofHeader(proof));
}

/** Anyone, without signing in: the comment stays up while a contributor reads what you send. */
export function reportPetitionComment(code: string, commentId: string,
                                      report: PetitionCommentReportRequest): Promise<PetitionReportFiled> {
  return postJson<PetitionReportFiled>(`${petitionPath(code)}/comments/${encodeURIComponent(commentId)}/report`, report);
}

/** The creator answers the MCE, once, on the number they started the petition with. The page comes back with it on. */
export function replyToResponse(code: string, text: string, proof: string): Promise<PetitionDetail> {
  return postJson<PetitionDetail>(`${petitionPath(code)}/reply`, { text }, proofHeader(proof));
}
