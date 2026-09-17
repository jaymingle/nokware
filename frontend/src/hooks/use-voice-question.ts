"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api/errors";
import { hearQuestion } from "@/lib/api/public";
import { VOICE_FAILED, VOICE_MAX_SECONDS, micProblem, recordingType } from "@/lib/ask/voice";

import type { AskHeard } from "@/lib/api/types";

export type VoiceState =
  | { kind: "idle" }
  | { kind: "recording"; seconds: number }
  | { kind: "listening" }
  | { kind: "heard"; heard: AskHeard }
  | { kind: "failed"; message: string };

type Session = { recorder: MediaRecorder; stream: MediaStream; timer: number; discard: boolean };

function finish(session: Session) {
  window.clearInterval(session.timer);
  session.stream.getTracks().forEach((track) => track.stop()); // the browser's "recording" light goes out
}

function halt(session: Session, discard: boolean) {
  session.discard ||= discard;
  if (session.recorder.state === "inactive") finish(session);
  else session.recorder.stop();
}

function useRecorder(onRecorded: (recording: Blob) => void, onTick: (seconds: number) => void) {
  const session = useRef<Session | null>(null);
  useEffect(() => () => void (session.current && halt(session.current, true)), []);

  const record = useCallback(
    (stream: MediaStream) => {
      const type = recordingType();
      const recorder = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
      const chunks: Blob[] = [];
      const started = Date.now();
      const current: Session = { recorder, stream, discard: false, timer: 0 };
      current.timer = window.setInterval(() => {
        const seconds = Math.floor((Date.now() - started) / 1000);
        if (seconds >= VOICE_MAX_SECONDS) halt(current, false);
        else onTick(seconds);
      }, 250);
      recorder.ondataavailable = (event) => void (event.data.size && chunks.push(event.data));
      recorder.onstop = () => {
        finish(current);
        if (session.current === current) session.current = null;
        if (!current.discard) onRecorded(new Blob(chunks, { type: recorder.mimeType || type }));
      };
      session.current = current;
      recorder.start();
    },
    [onRecorded, onTick],
  );

  const stop = useCallback((discard: boolean) => session.current && halt(session.current, discard), []);
  return { record, stop };
}

/** What was heard is shown back for the person to check: nothing is asked until they choose to. */
export function useVoiceQuestion() {
  const [state, setState] = useState<VoiceState>({ kind: "idle" });
  const attempt = useRef(0); // a recording cancelled while it is being heard must not come back

  const onRecorded = useCallback(async (recording: Blob) => {
    const mine = attempt.current;
    setState({ kind: "listening" });
    try {
      const heard = await hearQuestion(recording);
      if (attempt.current === mine) setState({ kind: "heard", heard });
    } catch (error) {
      if (attempt.current === mine) setState({ kind: "failed", message: error instanceof ApiError ? error.message : VOICE_FAILED });
    }
  }, []);
  const onTick = useCallback(
    (seconds: number) => setState((now) => (now.kind === "recording" && now.seconds === seconds ? now : { kind: "recording", seconds })),
    [],
  );
  const { record, stop } = useRecorder(onRecorded, onTick);

  const start = useCallback(async () => {
    attempt.current += 1;
    let stream: MediaStream | undefined;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      record(stream);
      setState({ kind: "recording", seconds: 0 });
    } catch (error) {
      stream?.getTracks().forEach((track) => track.stop());
      setState({ kind: "failed", message: micProblem(error) });
    }
  }, [record]);

  const cancel = useCallback(() => {
    attempt.current += 1;
    stop(true);
    setState({ kind: "idle" });
  }, [stop]);
  const done = useCallback(() => stop(false), [stop]);

  return { state, start, stop: done, cancel, clear: cancel };
}
