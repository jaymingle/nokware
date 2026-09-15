"use client";

import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

/** False on the server and during hydration, true after: for what only this browser's storage can say. */
export function useMounted(): boolean {
  return useSyncExternalStore(subscribe, () => true, () => false);
}
