"use client";

import { useCallback, useEffect, useRef, useState, type Dispatch, type SetStateAction } from "react";

import { AskError, FAILED_MESSAGE } from "@/lib/ask/ndjson";
import { streamAsk } from "@/lib/ask/stream";
import { applyEvent, failTurn, newTurn, type Turn } from "@/lib/ask/turn";

type SetTurns = Dispatch<SetStateAction<Turn[]>>;

/** Streams one answer into its turn, cancelling any answer still in progress. */
function useAnswerRunner(setTurns: SetTurns) {
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  return useCallback(
    async (id: string, question: string) => {
      const update = (change: (turn: Turn) => Turn) =>
        setTurns((current) => current.map((turn) => (turn.id === id ? change(turn) : turn)));
      controller.current?.abort();
      const abort = new AbortController();
      controller.current = abort;
      try {
        await streamAsk(question, (event) => update((turn) => applyEvent(turn, event)), abort.signal);
      } catch (error) {
        if (abort.signal.aborted) return;
        update((turn) => failTurn(turn, error instanceof AskError ? error.message : FAILED_MESSAGE));
      }
    },
    [setTurns],
  );
}

/**
 * The page's questions and answers. Each question is answered on its own (the
 * API keeps no conversation), one at a time; leaving the page cancels the
 * answer in progress.
 */
export function useAskThread() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const counter = useRef(0);
  const run = useAnswerRunner(setTurns);

  const ask = useCallback(
    (question: string): string => {
      counter.current += 1;
      const id = `turn-${counter.current}`;
      setTurns((current) => [...current, newTurn(id, question)]);
      void run(id, question);
      return id;
    },
    [run],
  );

  const retry = useCallback(
    (turn: Turn) => {
      setTurns((current) => current.map((t) => (t.id === turn.id ? newTurn(turn.id, turn.question) : t)));
      void run(turn.id, turn.question);
    },
    [run],
  );

  const busy = turns.some((turn) => turn.stage === "searching" || turn.stage === "writing");
  return { turns, ask, retry, busy };
}
