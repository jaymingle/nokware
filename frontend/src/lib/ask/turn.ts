import { markFiguresCited } from "@/lib/ask/figures";
import { groupSources, markCited, type SourceDocument } from "@/lib/ask/sources";

import type { AnswerStatus, AskChart, AskFigure, AskStreamEvent, ExportView } from "@/lib/api/types";

/** counting: searching the Ledger and counting live report data at once. */
export type TurnStage = "searching" | "counting" | "writing" | "done" | "error";

/** One question and its answer as it arrives. */
export type Turn = {
  id: string;
  question: string;
  stage: TurnStage;
  documents: SourceDocument[];
  /** Live counts of reports residents filed: sources, but not documents. */
  figures: AskFigure[];
  /** The raw text while it streams; replaced by the checked answer when done. */
  text: string;
  status: AnswerStatus | null;
  error: string | null;
  /** A chart the question asked for, of the cited live figures; the API decides its kind and values. */
  chart: AskChart | null;
  /** Why the chart isn't the kind asked for, or why there is none. */
  chartNote: string | null;
  /** The answer as the export route takes it back, signed by the API. */
  exportView: ExportView | null;
  /** Whether the API will read it aloud: never an answer about someone's safety. */
  speakable: boolean;
};

export function newTurn(id: string, question: string): Turn {
  return {
    id, question, stage: "searching", documents: [], figures: [], text: "", status: null, error: null,
    chart: null, chartNote: null, exportView: null, speakable: false,
  };
}

/** The turn after one stream event. */
export function applyEvent(turn: Turn, event: AskStreamEvent): Turn {
  switch (event.type) {
    case "stage":
      return { ...turn, stage: event.stage };
    case "sources":
      return { ...turn, documents: groupSources(event.sources), figures: event.figures ?? [] };
    case "delta":
      return { ...turn, stage: "writing", text: turn.text + event.text };
    case "done":
      return {
        ...turn,
        stage: "done",
        text: event.answer,
        status: event.status,
        documents: markCited(turn.documents, event.cited),
        figures: markFiguresCited(turn.figures, event.cited),
        chart: event.chart ?? null,
        chartNote: event.chart_note ?? null,
        exportView: event.export ?? null,
        speakable: event.speakable ?? false,
      };
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
