"use client";

import { useEffect, useState } from "react";

const TICK_MS = 15_000;

/** The current time, updated every 15 seconds so countdowns stay live. */
export function useNow(): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), TICK_MS);
    return () => clearInterval(timer);
  }, []);
  return now;
}
