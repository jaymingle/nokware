import { describe, expect, it } from "vitest";

import { applyEvent, attribution, citedDocuments, newTurn } from "@/lib/ask/turn";

import type { AskFigure, AskSource, AskStreamEvent } from "@/lib/api/types";

const source = (label: string) => ({ label, cited: false, document_id: label, title: label, chunk_text: "t" }) as AskSource;

function play(events: AskStreamEvent[]) {
  return events.reduce(applyEvent, newTurn("t1", "Q?"));
}

describe("applyEvent", () => {
  it("builds the answer from the stream, then replaces it with the checked answer", () => {
    const turn = play([
      { type: "stage", stage: "searching" },
      { type: "sources", sources: [source("S1"), source("S2")], figures: [] },
      { type: "stage", stage: "writing" },
      { type: "delta", text: "Yes [S1]" },
      { type: "delta", text: " and [S7]." },
    ]);
    expect([turn.stage, turn.text, turn.documents.length]).toEqual(["writing", "Yes [S1] and [S7].", 2]);

    const done = applyEvent(turn, { type: "done", answer: "Yes [S1] and.", answer_english: "Yes [S1] and.",
      language: "en", translated: false, status: "answered", cited: ["S1"], speakable: true });
    expect([done.stage, done.text, done.status]).toEqual(["done", "Yes [S1] and.", "answered"]);
    expect([done.english, done.translated]).toEqual(["Yes [S1] and.", false]);
    expect(citedDocuments(done).map((doc) => doc.label)).toEqual(["S1"]);
    expect([done.chart, done.chartNote, done.exportView, done.speakable]).toEqual([null, null, null, true]);
  });

  it("keeps the English beside an answer a machine translated", () => {
    const turn = play([
      { type: "sources", sources: [source("S1")], figures: [] },
      { type: "done", answer: "Oui [S1].", answer_english: "Yes [S1].", language: "fr", translated: true,
        status: "answered", cited: ["S1"], speakable: false },
    ]);
    expect([turn.text, turn.english, turn.translated, turn.speakable]).toEqual(["Oui [S1].", "Yes [S1].", true, false]);
  });

  it("keeps the question when the answer fails", () => {
    const turn = play([{ type: "stage", stage: "searching" }, { type: "error", message: "Ask is busy right now." }]);
    expect([turn.stage, turn.error, turn.question]).toEqual(["error", "Ask is busy right now.", "Q?"]);
  });
});

describe("attribution", () => {
  const figure = (label: string, source: "reports" | "documents") =>
    ({ label, cited: true, description: label, value: "1", rows: [], grouped_by: "none", source, counted_at: null }) as AskFigure;

  function answered(sources: AskSource[], figures: AskFigure[], cited: string[]) {
    return play([{ type: "sources", sources, figures },
      { type: "done", answer: "a", answer_english: "a", language: "en", translated: false, status: "answered", cited, speakable: true }]);
  }

  it("names a budget figure as what it is: read from a document, not counted from reports", () => {
    // It read "Answered from 2 live report figures" for two figures taken out of two budget PDFs.
    const turn = answered([], [figure("B1", "documents"), figure("B2", "documents")], ["B1", "B2"]);
    expect(attribution(turn)).toBe("Answered from 2 budget figures");
  });

  it("counts each kind apart when an answer rests on more than one", () => {
    const turn = answered([source("S1")], [figure("B1", "documents"), figure("R1", "reports")], ["S1", "B1", "R1"]);
    expect(attribution(turn)).toBe("Answered from 1 document in the Ledger and 1 budget figure and 1 live report figure");
  });

  it("counts only what the answer cited, and says nothing when it cited none", () => {
    const turn = answered([source("S1")], [figure("R1", "reports")], ["R1"]);
    expect(attribution(turn)).toBe("Answered from 1 live report figure");
    expect(attribution(answered([source("S1")], [], []))).toBeNull();
  });
});
