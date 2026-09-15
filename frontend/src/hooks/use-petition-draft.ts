"use client";

import { useEffect, useState } from "react";

import { keepDraft, keptDraft } from "@/lib/petitions";

import type { OwnPetition, PetitionDraft } from "@/lib/api/types";

export type DraftState = {
  title: string;
  body: string;
  topic: string;
  scope: "metro" | "area";
  ward: string;
  issue: string | null;
  documents: string[];
};

export const EMPTY_DRAFT: DraftState = { title: "", body: "", topic: "", scope: "area", ward: "", issue: null, documents: [] };

/** The draft as the API takes it. */
export function toRequest(draft: DraftState): PetitionDraft {
  return {
    title: draft.title, body: draft.body, topic: draft.topic, scope: draft.scope,
    ward: draft.scope === "area" ? draft.ward || null : null, issue: draft.issue, documents: draft.documents,
  };
}

/** A refused petition, back in the form for editing. */
export function fromPetition(petition: OwnPetition): DraftState {
  return { title: petition.title, body: petition.body, topic: petition.topic_id, scope: petition.scope, ward: petition.ward_id ?? "",
    issue: petition.issue_id, documents: petition.document_ids };
}

/** What a check was run on: when the words or topic change, the draft is checked again. */
export function checkKey(draft: DraftState): string {
  return JSON.stringify([draft.title.trim(), draft.body.trim(), draft.topic]);
}

/**
 * The new petition being written, kept in this browser as it changes (so confirming a phone on WhatsApp, or a
 * reload, loses nothing). An issue linked from the issue list starts it off.
 */
export function usePetitionDraft(issue: string | null): [DraftState, (change: Partial<DraftState>) => void, () => void] {
  const [draft, setDraft] = useState<DraftState>(() => {
    const kept = typeof window === "undefined" ? null : keptDraft<DraftState>();
    return { ...EMPTY_DRAFT, ...kept, ...(issue ? { issue } : {}) };
  });
  useEffect(() => keepDraft(draft), [draft]);
  const change = (next: Partial<DraftState>) => setDraft((current) => ({ ...current, ...next }));
  const clear = () => {
    keepDraft(null);
    setDraft(EMPTY_DRAFT);
  };
  return [draft, change, clear];
}
