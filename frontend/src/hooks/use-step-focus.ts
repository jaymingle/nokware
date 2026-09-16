import { useEffect, useRef, type RefObject } from "react";

/**
 * Carries the focus into a step that has replaced another.
 *
 * Without it the control the person pressed is unmounted and the focus falls
 * to the top of the document: someone filing a report with a keyboard presses
 * "No, it's a problem in my area" and then has to tab through the whole header
 * again to reach the form they just asked for. The first render is left alone,
 * because arriving on the page is not a step.
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
