import { describe, expect, it } from "vitest";

import { applyEvent, citedDocuments, newTurn } from "@/lib/ask/turn";

import type { AskSource, AskStreamEvent } from "@/lib/api/types";

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

    const done = applyEvent(turn, { type: "done", answer: "Yes [S1] and.", status: "answered", cited: ["S1"] });
    expect([done.stage, done.text, done.status]).toEqual(["done", "Yes [S1] and.", "answered"]);
    expect(citedDocuments(done).map((doc) => doc.label)).toEqual(["S1"]);
  });

  it("keeps the question when the answer fails", () => {
    const turn = play([{ type: "stage", stage: "searching" }, { type: "error", message: "Ask is busy right now." }]);
    expect([turn.stage, turn.error, turn.question]).toEqual(["error", "Ask is busy right now.", "Q?"]);
  });
});
