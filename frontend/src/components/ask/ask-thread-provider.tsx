"use client";

import { createContext, useContext, type ReactNode } from "react";

import { useAskThread } from "@/hooks/use-ask-thread";

type Thread = ReturnType<typeof useAskThread>;

const AskThreadContext = createContext<Thread | null>(null);

/**
 * One conversation for the tab: the /ask page and the panel opened from any public page share it, so a question
 * asked in the panel is still there on the page, and closing the panel doesn't throw an answer away. It lasts as
 * long as the tab; the API still keeps no conversation, and each question is answered on its own.
 */
export function AskThreadProvider({ children }: { children: ReactNode }) {
  return <AskThreadContext.Provider value={useAskThread()}>{children}</AskThreadContext.Provider>;
}

export function useThread(): Thread {
  const thread = useContext(AskThreadContext);
  if (!thread) throw new Error("Ask needs an AskThreadProvider above it");
  return thread;
}
