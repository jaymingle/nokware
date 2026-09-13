"use client";

import { useEffect } from "react";
import { LogOutIcon } from "lucide-react";

import { Button } from "@/components/ui/button";

// Somewhere unremarkable to land. replace() swaps this page out of the tab's
// history, so Back doesn't return to it.
const NEUTRAL_SITE = "https://www.google.com/";
const SHIFT_PRESSES = 3;
const SHIFT_WINDOW_MS = 2_000;

function leave() {
  window.location.replace(NEUTRAL_SITE);
}

/** Pressing Shift three times in quick succession leaves too (the GOV.UK "exit this page" pattern). */
function useShiftToLeave() {
  useEffect(() => {
    let presses: number[] = [];
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Shift" || event.repeat) return;
      const now = Date.now();
      presses = [...presses.filter((t) => now - t < SHIFT_WINDOW_MS), now];
      if (presses.length >= SHIFT_PRESSES) leave();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}

/** Leaves for a neutral site at once, for someone who may be watched while reporting. */
export function QuickExit() {
  useShiftToLeave();
  return (
    <div className="sticky top-3 z-40 flex justify-end">
      <div className="flex flex-col items-end gap-1">
        <Button onClick={leave} className="bg-ink text-paper hover:bg-ink/85" data-testid="quick-exit">
          <LogOutIcon data-icon="inline-start" />
          Quick exit
        </Button>
        <span className="hidden rounded bg-paper/90 px-1 text-[11.5px] text-ink-soft sm:block">or press Shift 3 times</span>
      </div>
    </div>
  );
}
