import { groupSources, markCited, type SourceDocument } from "@/lib/ask/sources";

import type { AnswerStatus, AskStreamEvent } from "@/lib/api/types";

export type TurnStage = "searching" | "writing" | "done" | "error";

/** One question and its answer as it arrives. */
export type Turn = {
  id: string;
  question: string;
  stage: TurnStage;
  documents: SourceDocument[];
  /** The raw text while it streams; replaced by the checked answer when done. */
  text: string;
  status: AnswerStatus | null;
  error: string | null;
};

export function newTurn(id: string, question: string): Turn {
  return { id, question, stage: "searching", documents: [], text: "", status: null, error: null };
}

/** The turn after one stream event. */
export function applyEvent(turn: Turn, event: AskStreamEvent): Turn {
  switch (event.type) {
    case "stage":
      return { ...turn, stage: event.stage };
    case "sources":
      return { ...turn, documents: groupSources(event.sources) };
    case "delta":
      return { ...turn, stage: "writing", text: turn.text + event.text };
    case "done":
      return { ...turn, stage: "done", text: event.answer, status: event.status, documents: markCited(turn.documents, event.cited) };
    case "error":
      return failTurn(turn, event.message);
  }
}

export function failTurn(turn: Turn, message: string): Turn {
  return { ...turn, stage: "error", error: message };
}

export function citedDocuments(turn: Turn): SourceDocument[] {
  return turn.documents.filter((doc) => doc.cited);
}
