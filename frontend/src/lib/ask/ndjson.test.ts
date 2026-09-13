import { describe, expect, it } from "vitest";

import { AskError, parseEvent, takeLines } from "@/lib/ask/ndjson";

describe("takeLines", () => {
  it("keeps an unfinished line for the next chunk", () => {
    expect(takeLines('{"a":1}\n{"b"')).toEqual({ lines: ['{"a":1}'], rest: '{"b"' });
    expect(takeLines('{"a":1}\n\n{"b":2}\n')).toEqual({ lines: ['{"a":1}', '{"b":2}'], rest: "" });
  });
});

describe("parseEvent", () => {
  it("accepts known events and rejects anything else", () => {
    expect(parseEvent('{"type":"delta","text":"Hi"}')).toEqual({ type: "delta", text: "Hi" });
    expect(() => parseEvent('{"type":"surprise"}')).toThrow(AskError);
  });
});
