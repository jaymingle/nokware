// Without a timeout a stalled request leaves the button saying "Filing…" for as long as the network allows,
// and the resident never learns whether their report was filed.

/** Long enough for a slow reply, short enough that a stall is reported while the person is still there. */
export const REPLY_MS = 30_000;
/** Photos from a phone on a mobile connection: the upload itself is the wait. */
export const UPLOAD_MS = 120_000;

export const TIMED_OUT = "Nokware didn't answer in time. Check your connection and try again.";
export const TIMED_OUT_SENDING =
  "Nokware didn't answer in time. What you sent may still have gone through, so check before sending it again.";

function sends(init: RequestInit): boolean {
  const method = (init.method ?? "GET").toUpperCase();
  return method !== "GET" && method !== "HEAD";
}

export function timeoutFor(init: RequestInit): number {
  return init.body instanceof FormData ? UPLOAD_MS : REPLY_MS;
}

/** What to tell someone whose request ran out of time: a write may have been made, a read certainly wasn't. */
export function timedOutMessage(init: RequestInit): string {
  return sends(init) ? TIMED_OUT_SENDING : TIMED_OUT;
}

export function timedOut(error: unknown): boolean {
  return error instanceof DOMException && (error.name === "TimeoutError" || error.name === "AbortError");
}

/** The caller's own signal still applies: whichever aborts first wins. */
export function withTimeout(init: RequestInit): RequestInit {
  const limit = AbortSignal.timeout(timeoutFor(init));
  return { ...init, signal: init.signal ? AbortSignal.any([init.signal, limit]) : limit };
}
