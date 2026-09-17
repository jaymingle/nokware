"use client";

import { useCallback, useId } from "react";

import { AskComposer } from "@/components/ask/ask-composer";
import { useThread } from "@/components/ask/ask-thread-provider";
import { AskTurn } from "@/components/ask/ask-turn";
import { AskWelcome } from "@/components/ask/ask-welcome";
import { cn } from "@/lib/utils";

type AskChatMode = "page" | "panel";

// The newest exchange is at least a screen tall, so asking scrolls its question to the top and the answer grows
// below it, rather than the page following every word. On the page, a screen less the docked question box.
const LAST_TURN = { page: "min-h-[calc(100dvh-10rem)]", panel: "min-h-full" } as const;

/** One component for the /ask page, which scrolls with the window, and the panel, which scrolls inside itself. */
export function AskChat({ mode }: { mode: AskChatMode }) {
  const { turns, ask, retry, busy } = useThread();
  const scope = `ask-${useId().replace(/[^a-zA-Z0-9-]/g, "")}`;
  const panel = mode === "panel";
  const onAsk = useCallback(
    (question: string) => {
      const id = ask(question);
      requestAnimationFrame(() => document.getElementById(`${scope}-${id}`)?.scrollIntoView({ block: "start" }));
    },
    [ask, scope],
  );
  return (
    <div className={cn("flex flex-col", panel ? "h-full min-h-0" : "mx-auto -mb-10 w-full max-w-3xl flex-1")} data-testid={`ask-chat-${mode}`}>
      <div className={cn("flex flex-1 flex-col gap-8", panel ? "min-h-0 overflow-y-auto overscroll-contain px-4 pt-5 pb-6" : "pb-8")}
        data-testid="ask-thread">
        {turns.length === 0 ? <AskWelcome compact={panel} onAsk={onAsk} disabled={busy} /> : null}
        {turns.length > 0 && !panel ? <h1 className="sr-only">Ask Nokware</h1> : null}
        {turns.map((turn, index) => (
          <div key={turn.id} className={cn(index === turns.length - 1 && LAST_TURN[mode])}>
            <AskTurn turn={turn} scope={scope} onRetry={retry} />
          </div>
        ))}
      </div>
      <AskComposer busy={busy} onAsk={onAsk} started={turns.length > 0} panel={panel} />
    </div>
  );
}
