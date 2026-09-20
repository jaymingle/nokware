"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const HIGHLIGHT_MS = 2400;

/** The sources sit in a closed disclosure, so a citation has to open it before there is anything to scroll to. */
function reveal(id: string): void {
  const card = document.getElementById(id);
  if (!card) return;
  const smooth = !window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  card.scrollIntoView({ behavior: smooth ? "smooth" : "auto", block: "center" });
  card.focus({ preventScroll: true });
}

export function useAskSourceJump(anchorPrefix: string) {
  const [highlighted, setHighlighted] = useState<string | null>(null);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  const anchorFor = useCallback((label: string) => `${anchorPrefix}-${label}`, [anchorPrefix]);
  const jump = useCallback(
    (label: string) => {
      setSourcesOpen(true);
      setHighlighted(label);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setHighlighted(null), HIGHLIGHT_MS);
      // A frame later: the disclosure and the source's own row have to be open before either can be scrolled to.
      requestAnimationFrame(() => requestAnimationFrame(() => reveal(anchorFor(label))));
    },
    [anchorFor],
  );
  return { highlighted, sourcesOpen, setSourcesOpen, anchorFor, jump };
}

export type AskSourceJump = ReturnType<typeof useAskSourceJump>;
