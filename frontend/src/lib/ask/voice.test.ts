import { describe, expect, it } from "vitest";

import { MIC_BLOCKED, MIC_FAILED, NO_MIC, formatSeconds, micProblem } from "@/lib/ask/voice";

describe("a spoken question", () => {
  it("says why the microphone couldn't be opened, in words for the person", () => {
    expect(micProblem(new DOMException("denied", "NotAllowedError"))).toBe(MIC_BLOCKED);
    expect(micProblem(new DOMException("insecure", "SecurityError"))).toBe(MIC_BLOCKED);
    expect(micProblem(new DOMException("none", "NotFoundError"))).toBe(NO_MIC);
    expect(micProblem(new Error("anything else"))).toBe(MIC_FAILED);
  });

  it("shows the recording's length as minutes and seconds", () => {
    expect(formatSeconds(0)).toBe("0:00");
    expect(formatSeconds(7)).toBe("0:07");
    expect(formatSeconds(60)).toBe("1:00");
  });
});
