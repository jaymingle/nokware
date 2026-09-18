import { describe, expect, it } from "vitest";

import { REPLY_MS, TIMED_OUT, TIMED_OUT_SENDING, UPLOAD_MS, timedOut, timedOutMessage, timeoutFor, withTimeout } from "@/lib/api/timeout";

describe("a request that runs out of time", () => {
  it("allows longer for photos than for a reply", () => {
    expect(timeoutFor({ method: "POST", body: new FormData() })).toBe(UPLOAD_MS);
    expect(timeoutFor({ method: "POST", body: "{}" })).toBe(REPLY_MS);
    expect(timeoutFor({})).toBe(REPLY_MS);
  });

  it("warns that a filing may have gone through, but never says that about a read", () => {
    expect(timedOutMessage({ method: "POST", body: new FormData() })).toBe(TIMED_OUT_SENDING);
    expect(timedOutMessage({})).toBe(TIMED_OUT);
    expect(timedOutMessage({ method: "GET" })).toBe(TIMED_OUT);
  });

  it("knows a timeout from any other failure", () => {
    expect(timedOut(new DOMException("timed out", "TimeoutError"))).toBe(true);
    expect(timedOut(new DOMException("aborted", "AbortError"))).toBe(true);
    expect(timedOut(new TypeError("Failed to fetch"))).toBe(false);
  });

  it("keeps the caller's own signal", () => {
    const own = new AbortController();
    const init = withTimeout({ method: "POST", signal: own.signal, body: "{}" });
    expect(init.signal?.aborted).toBe(false);
    own.abort();
    expect(init.signal?.aborted).toBe(true);
  });
});
