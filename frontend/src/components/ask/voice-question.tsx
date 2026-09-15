"use client";

import { LoaderCircleIcon, MicIcon, SquareIcon, XIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useMounted } from "@/hooks/use-mounted";
import { VOICE_MAX_SECONDS, canRecord, formatSeconds } from "@/lib/ask/voice";

import type { VoiceState } from "@/hooks/use-voice-question";

type ControlProps = { state: VoiceState; onStart: () => void; onStop: () => void; onCancel: () => void };

function Recording({ seconds, onStop, onCancel }: { seconds: number; onStop: () => void; onCancel: () => void }) {
  return (
    <div className="flex h-11 min-w-0 flex-1 items-center gap-1 rounded-lg border border-brick/30 bg-brick-tint ps-3 pe-1" data-testid="ask-voice-recording">
      <span className="size-2 shrink-0 rounded-full bg-brick motion-safe:animate-pulse" aria-hidden />
      <span className="me-auto truncate ps-1 text-[13.5px] text-ink tabular-nums" aria-live="off" data-testid="ask-voice-timer">
        <span className="max-sm:sr-only">Recording </span>
        {formatSeconds(seconds)} / {formatSeconds(VOICE_MAX_SECONDS)}
      </span>
      <Button type="button" variant="ghost" size="icon-sm" onClick={onCancel} aria-label="Discard the recording" data-testid="ask-voice-cancel">
        <XIcon />
      </Button>
      <Button type="button" size="sm" onClick={onStop} data-testid="ask-voice-stop">
        <SquareIcon data-icon="inline-start" className="fill-current" />
        Done
      </Button>
    </div>
  );
}

/** The microphone beside the question box: record a question instead of typing it. Hidden where recording can't work.
 * While recording, it takes the box's place (the composer hides the box), so it fits a phone. */
export function VoiceControl({ state, onStart, onStop, onCancel }: ControlProps) {
  const mounted = useMounted();
  if (!mounted || !canRecord()) return null;
  if (state.kind === "recording") return <Recording seconds={state.seconds} onStop={onStop} onCancel={onCancel} />;
  const listening = state.kind === "listening";
  return (
    <Button type="button" variant="secondary" className="h-11 w-11 shrink-0 px-0" onClick={onStart} disabled={listening}
      aria-label={listening ? "Listening to your question…" : "Ask by speaking"} data-testid="ask-voice-start">
      {listening ? <LoaderCircleIcon className="motion-safe:animate-spin" /> : <MicIcon />}
    </Button>
  );
}

type CheckProps = { state: VoiceState; busy: boolean; onAsk: (question: string) => void; onEdit: (question: string) => void;
  onDismiss: () => void; onRetry: () => void };

/** What was heard, shown back before anything is asked, so a mishearing or a bad translation is caught. */
export function VoiceCheck({ state, busy, onAsk, onEdit, onDismiss, onRetry }: CheckProps) {
  if (state.kind === "listening") {
    return <p className="mb-2 text-[13px] text-ink-muted" role="status" data-testid="ask-voice-listening">Listening to your question…</p>;
  }
  if (state.kind === "failed") {
    return (
      <div role="alert" className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-brick/30 bg-brick-tint px-3 py-2 text-[13.5px] text-ink" data-testid="ask-voice-error">
        <span className="flex-1">{state.message}</span>
        <span className="flex gap-1">
          <Button type="button" variant="ghost" size="sm" onClick={onRetry} data-testid="ask-voice-retry">Try again</Button>
          <Button type="button" variant="ghost" size="sm" onClick={onDismiss} data-testid="ask-voice-dismiss">Close</Button>
        </span>
      </div>
    );
  }
  if (state.kind !== "heard") return null;
  const { question, understood } = state.heard;
  return (
    <div className="mb-2 rounded-lg border border-teal/25 bg-teal-tint px-3.5 py-3" data-testid="ask-voice-heard">
      <p className="text-[14.5px] leading-snug text-ink" data-testid="ask-voice-understood">{understood}</p>
      <p className="mt-1 text-[12.5px] text-ink-muted">Check it: nothing is asked until you choose.</p>
      <div className="mt-2.5 flex flex-wrap gap-2">
        <Button type="button" size="sm" onClick={() => onAsk(question)} disabled={busy} data-testid="ask-voice-confirm">Ask this</Button>
        <Button type="button" variant="secondary" size="sm" onClick={() => onEdit(question)} data-testid="ask-voice-edit">Edit</Button>
        <Button type="button" variant="ghost" size="sm" onClick={onDismiss} data-testid="ask-voice-discard">Discard</Button>
      </div>
    </div>
  );
}
