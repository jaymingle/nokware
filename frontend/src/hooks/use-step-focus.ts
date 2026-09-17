import { useEffect, useRef, type RefObject } from "react";

/**
 * When a step replaces another, the control the person pressed is unmounted and
 * focus falls to the top of the document, so a keyboard user has to tab through
 * the header again. The first render is left alone: arriving is not a step.
 *
 * Give the returned ref to a wrapper with tabIndex={-1} around the step.
 */
export function useStepFocus<T extends HTMLElement>(step: string): RefObject<T | null> {
  const box = useRef<T>(null);
  const previous = useRef(step);
  useEffect(() => {
    if (previous.current !== step) box.current?.focus();
    previous.current = step;
  }, [step]);
  return box;
}
