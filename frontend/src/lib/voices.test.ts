import { describe, expect, it } from "vitest";

import { makeToken, voicesLine, voicesTally } from "@/lib/voices";

describe("voices", () => {
  it("makes a URL-safe token the server accepts", () => {
    const token = makeToken(new Uint8Array(24).fill(251));
    expect(token).toMatch(/^[A-Za-z0-9_-]{16,128}$/);
    expect(token).toHaveLength(32);
  });

  it("says the count in words", () => {
    expect([voicesLine(0), voicesLine(1), voicesLine(14)]).toEqual([
      "No one has added their voice yet",
      "1 resident says this affects them",
      "14 residents say this affects them",
    ]);
    expect([voicesTally(1), voicesTally(3)]).toEqual(["1 resident added their voice", "3 residents added their voice"]);
  });
});
