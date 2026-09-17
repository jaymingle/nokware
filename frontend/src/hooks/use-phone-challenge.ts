"use client";

import { useCallback, useEffect, useState } from "react";

import { newPhoneChallenge, phoneChallengeStatus } from "@/lib/api/petitions";
import { keepChallenge, keepProof, keptChallenge, type KeptChallenge, type KeptProof } from "@/lib/petitions";

import type { PhoneChallengeStatus } from "@/lib/api/types";

const POLL_MS = 3_000;

type PhoneChallengeState = {
  challenge: KeptChallenge | null;
  starting: boolean;
  error: string | null;
  start: () => Promise<void>;
  cancel: () => void;
  settle: (status: PhoneChallengeStatus) => void;
};

/** Ask about the challenge every few seconds until it is confirmed or has expired. */
function usePolling(challenge: KeptChallenge | null, onStatus: (status: PhoneChallengeStatus) => void) {
  useEffect(() => {
    if (!challenge) return;
    const timer = setInterval(async () => {
      try {
        onStatus(await phoneChallengeStatus(challenge.challenge));
      } catch {
        // A missed poll is tried again on the next tick.
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [challenge, onStatus]);
}

/**
 * A code for this page to have confirmed, kept in the tab (so switching to WhatsApp and back, or reloading,
 * keeps it) until WhatsApp, USSD or an SMS code confirms it.
 */
export function usePhoneChallenge(onConfirmed: (proof: KeptProof) => void): PhoneChallengeState {
  const [challenge, setChallenge] = useState<KeptChallenge | null>(() => (typeof window === "undefined" ? null : keptChallenge(Date.now())));
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const replace = useCallback((next: KeptChallenge | null) => {
    keepChallenge(next);
    setChallenge(next);
  }, []);
  const settle = useCallback((status: PhoneChallengeStatus) => {
    if (status.state === "expired") {
      replace(null);
      setError("That code has expired. Get a new one.");
      return;
    }
    if (status.state !== "proven" || !status.proof || !status.number || !status.expires_at) return;
    const proof = { token: status.proof, number: status.number, expiresAt: status.expires_at };
    keepProof(proof);
    replace(null);
    onConfirmed(proof);
  }, [onConfirmed, replace]);
  usePolling(challenge, settle);
  const start = async () => {
    setStarting(true);
    setError(null);
    try {
      replace({ ...(await newPhoneChallenge()), startedAt: Date.now() });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Couldn't get a code. Try again.");
    } finally {
      setStarting(false);
    }
  };
  return { challenge, starting, error, start, cancel: () => replace(null), settle };
}
