"use client";

import { LoaderCircleIcon, PauseIcon, Volume2Icon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useReadAloud, type ReadAloudState } from "@/hooks/use-read-aloud";

import type { SpokenPart } from "@/lib/api/public";

const LABELS: Record<ReadAloudState, string> = { idle: "Listen", loading: "Preparing the audio…", playing: "Pause", paused: "Resume" };

/**
 * A speaker button for one block of prose someone may not be able to read: an Ask answer, a report's confirmation
 * or its status. Not a whole-page reader (screen readers do that better). The audio is made by the API from what it
 * produced, never from text on the page, a part at a time.
 */
export function ReadAloud({ load, label, testId }: { load: (part: number) => Promise<SpokenPart>; label: string; testId: string }) {
  const { state, error, resuming, toggle } = useReadAloud(load);
  const text = resuming ? "Continue" : LABELS[state];
  const Icon = state === "loading" ? LoaderCircleIcon : state === "playing" ? PauseIcon : Volume2Icon;
  return (
    <div className="flex flex-col gap-1">
      <Button variant="secondary" size="sm" className="w-fit" onClick={toggle} disabled={state === "loading"}
        aria-label={state === "idle" && !resuming ? label : text} data-testid={testId}>
        <Icon data-icon="inline-start" className={state === "loading" ? "animate-spin" : undefined} />
        {text}
      </Button>
      <p className="sr-only" aria-live="polite">{state === "playing" ? "Reading aloud" : state === "paused" ? "Paused" : ""}</p>
      {error ? <p role="alert" className="text-[12.5px] text-brick" data-testid={`${testId}-error`}>{error}</p> : null}
    </div>
  );
}
