"use client";

import { createContext, useContext, type ReactNode } from "react";

import { useAskThread } from "@/hooks/use-ask-thread";

type Thread = ReturnType<typeof useAskThread>;

const AskThreadContext = createContext<Thread | null>(null);

/** Shared by the /ask page and the panel, so closing the panel doesn't throw an answer away. */
export function AskThreadProvider({ children }: { children: ReactNode }) {
  return <AskThreadContext.Provider value={useAskThread()}>{children}</AskThreadContext.Provider>;
}

export function useThread(): Thread {
  const thread = useContext(AskThreadContext);
  if (!thread) throw new Error("Ask needs an AskThreadProvider above it");
  return thread;
}
