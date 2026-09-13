import { AskError, CUT_OFF_MESSAGE, FAILED_MESSAGE, OFFLINE_MESSAGE, TOO_LONG_MESSAGE, parseEvent, takeLines } from "@/lib/ask/ndjson";
import { env } from "@/lib/env";

import type { AskStreamEvent } from "@/lib/api/types";

async function open(question: string, signal: AbortSignal): Promise<ReadableStream<Uint8Array>> {
  let response: Response;
  try {
    response = await fetch(`${env.apiUrl}/api/ask/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal,
    });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new AskError(OFFLINE_MESSAGE);
  }
  if (response.status === 422) throw new AskError(TOO_LONG_MESSAGE);
  if (!response.ok || !response.body) throw new AskError(FAILED_MESSAGE);
  return response.body;
}

async function read(reader: ReadableStreamDefaultReader<Uint8Array>, signal: AbortSignal) {
  try {
    return await reader.read();
  } catch (error) {
    if (signal.aborted) throw error;
    throw new AskError(CUT_OFF_MESSAGE); // the connection dropped mid-answer
  }
}

/**
 * Asks the Ledger and reports each event as it arrives. Resolves once the
 * stream ends; throws AskError if it can't start or ends without an answer.
 */
export async function streamAsk(question: string, onEvent: (event: AskStreamEvent) => void, signal: AbortSignal): Promise<void> {
  const reader = (await open(question, signal)).getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;
  const emit = (line: string) => {
    const event = parseEvent(line);
    finished ||= event.type === "done" || event.type === "error";
    onEvent(event);
  };
  for (;;) {
    const { value, done } = await read(reader, signal);
    if (done) break;
    const { lines, rest } = takeLines(buffer + decoder.decode(value, { stream: true }));
    buffer = rest;
    lines.forEach(emit);
  }
  if (buffer.trim()) emit(buffer);
  if (!finished) throw new AskError(CUT_OFF_MESSAGE);
}
