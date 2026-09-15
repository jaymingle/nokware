"use client";

import { useCallback, useState } from "react";

import { useMounted } from "@/hooks/use-mounted";
import { useNow } from "@/hooks/use-now";
import { keepProof, keptProof, type KeptProof } from "@/lib/petitions";

export type PhoneProof = {
  ready: boolean; // false until this browser's storage has been read
  proof: KeptProof | null;
  confirm: (proof: KeptProof) => void;
  forget: () => void;
};

/** The phone this tab has confirmed, if any: kept in the tab, forgotten on request or once it expires. */
export function usePhoneProof(): PhoneProof {
  const mounted = useMounted();
  const now = useNow();
  const [chosen, setChosen] = useState<KeptProof | null | undefined>(undefined);
  const kept = chosen === undefined ? (mounted ? keptProof(now) : null) : chosen;
  const proof = kept && Date.parse(kept.expiresAt) > now ? kept : null;
  const confirm = useCallback((next: KeptProof) => setChosen(next), []);
  const forget = useCallback(() => {
    keepProof(null);
    setChosen(null);
  }, []);
  return { ready: mounted, proof, confirm, forget };
}
