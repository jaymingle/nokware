"use client";

import { LoaderCircleIcon, PauseIcon, Volume2Icon } from "lucide-react";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { useReadAloud, type ReadAloudState } from "@/hooks/use-read-aloud";

import type { SpokenPart } from "@/lib/api/public";

const INTENT_MS = 250; // long enough that passing over the button doesn't start making audio

const LABELS: Record<ReadAloudState, string> = { idle: "Listen", loading: "Preparing the audio…", playing: "Pause", paused: "Resume" };

/**
 * One block of prose, not the whole page: screen readers do that better. The API makes the audio from what it
 * produced, never from text on the page.
 */
export function ReadAloud({ load, label, testId }: { load: (part: number) => Promise<SpokenPart>; label: string; testId: string }) {
  const { state, error, resuming, toggle, prefetch } = useReadAloud(load);
  // Making the audio takes the model several seconds, so it starts on the intent to press rather than the press.
  // A brush past the button shouldn't spend a turn of the daily limit, hence the pause before it begins.
  const waiting = useRef<ReturnType<typeof setTimeout> | null>(null);
  const stopWaiting = () => {
    if (waiting.current) clearTimeout(waiting.current);
    waiting.current = null;
  };
  useEffect(() => stopWaiting, []);
  const intent = () => {
    stopWaiting();
    waiting.current = setTimeout(prefetch, INTENT_MS);
  };
  const text = resuming ? "Continue" : LABELS[state];
  const Icon = state === "loading" ? LoaderCircleIcon : state === "playing" ? PauseIcon : Volume2Icon;
  return (
    <div className="flex flex-col gap-1">
      <Button variant="secondary" size="sm" className="w-fit" onClick={toggle} disabled={state === "loading"}
        onPointerEnter={intent} onPointerLeave={stopWaiting} onFocus={prefetch}
        aria-label={state === "idle" && !resuming ? label : text} data-testid={testId}>
        <Icon data-icon="inline-start" className={state === "loading" ? "animate-spin" : undefined} />
        {text}
      </Button>
      <p className="sr-only" aria-live="polite">{state === "playing" ? "Reading aloud" : state === "paused" ? "Paused" : ""}</p>
      {error ? <p role="alert" className="text-[12.5px] text-brick" data-testid={`${testId}-error`}>{error}</p> : null}
    </div>
  );
}
