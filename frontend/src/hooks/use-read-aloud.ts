"use client";

import { useEffect, useRef, useState } from "react";

import type { SpokenPart } from "@/lib/api/public";

export type ReadAloudState = "idle" | "loading" | "playing" | "paused";

const NEXT_FAILED = "The next part couldn't be made just now. Press Continue to carry on from there.";

let current: HTMLAudioElement | null = null; // one reading at a time on the page

/**
 * While one part plays the next two are made, so a short part followed by a long one leaves no silence. One audio
 * element throughout, made on the first press, so later parts play without another press.
 */
export function useReadAloud(load: (part: number) => Promise<SpokenPart>) {
  const [state, setState] = useState<ReadAloudState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [resumeAt, setResumeAt] = useState(0);
  const player = useRef<HTMLAudioElement | null>(null);
  const pending = useRef(new Map<number, Promise<SpokenPart>>());
  useEffect(() => () => {
    player.current?.pause();
    if (player.current?.src) URL.revokeObjectURL(player.current.src);
  }, []);

  const fetchPart = (part: number) => {
    const known = pending.current.get(part);
    if (known) return known;
    const request = load(part);
    request.catch(() => pending.current.delete(part)); // a failed part is asked again next time
    pending.current.set(part, request);
    return request;
  };
  const start = async (audio: HTMLAudioElement) => {
    if (current && current !== audio) current.pause();
    current = audio;
    await audio.play();
    setState("playing");
  };
  const playBlob = (audio: HTMLAudioElement, blob: Blob, onEnded: () => void) => {
    if (audio.src) URL.revokeObjectURL(audio.src);
    audio.src = URL.createObjectURL(blob);
    audio.onended = onEnded;
    audio.onpause = () => setState((s) => (s === "playing" && !audio.ended ? "paused" : s));
    return start(audio);
  };
  const play = async (part: number, audio: HTMLAudioElement): Promise<void> => {
    setState("loading");
    setError(null);
    if (part === 0) void fetchPart(1); // made alongside the first: the first is short and ends before a second is ready
    try {
      const spoken = await fetchPart(part);
      pending.current.delete(part);
      const more = part + 1 < spoken.parts;
      for (const ahead of [part + 1, part + 2]) if (ahead < spoken.parts) void fetchPart(ahead);
      await playBlob(audio, spoken.audio, () => (more ? void play(part + 1, audio) : finish()));
    } catch (failure) {
      setState("idle");
      setResumeAt(part);
      setError(part > 0 ? NEXT_FAILED : failure instanceof Error ? failure.message : "The audio couldn't be played.");
    }
  };
  const finish = () => {
    pending.current.clear();
    setResumeAt(0);
    setState("idle");
  };
  const toggle = () => {
    const audio = (player.current ??= new Audio());
    if (state === "playing") audio.pause();
    else if (state === "paused") start(audio).catch(() => setState("paused"));
    else void play(resumeAt, audio);
  };
  return { state, error, resuming: state === "idle" && resumeAt > 0, toggle };
}
