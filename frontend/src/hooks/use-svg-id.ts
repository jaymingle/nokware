"use client";

import { useId } from "react";

/** A stable id, stripped of the colons useId adds, so it works inside an SVG `url(#…)` or a CSS selector. */
export function useSvgId(prefix: string): string {
  return `${prefix}-${useId().replace(/[^a-zA-Z0-9-]/g, "")}`;
}
