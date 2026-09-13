// Parsing for POST /api/ask/stream's newline-delimited JSON, kept free of
// runtime config so it can be unit-tested on its own.
import type { AskStreamEvent } from "@/lib/api/types";

const EVENT_TYPES = new Set(["stage", "sources", "delta", "done", "error"]);

export const OFFLINE_MESSAGE = "Couldn't reach Nokware. Check your connection and try again.";
export const CUT_OFF_MESSAGE = "The answer was cut off before it finished. Try again.";
export const TOO_LONG_MESSAGE = "Ask a question of up to 1,000 characters.";
export const FAILED_MESSAGE = "Something went wrong while answering. Try again.";

/** A failure the reader can act on; the message is safe to show. */
export class AskError extends Error {}

/** Complete lines from a growing buffer, and the unfinished remainder to keep. */
export function takeLines(buffer: string): { lines: string[]; rest: string } {
  const parts = buffer.split("\n");
  const rest = parts.pop() ?? "";
  return { lines: parts.filter((line) => line.trim() !== ""), rest };
}

export function parseEvent(line: string): AskStreamEvent {
  const event: unknown = JSON.parse(line);
  if (typeof event !== "object" || event === null || !EVENT_TYPES.has(String((event as { type?: unknown }).type))) {
    throw new AskError(FAILED_MESSAGE);
  }
  return event as AskStreamEvent;
}
