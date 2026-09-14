// One voice per browser per issue: a random token this browser keeps (the server stores only a hash of it
// with the issue), and the issues it has already added its voice to, so the button can say so.
const TOKEN_KEY = "nokware-voice-token";
const VOICED_KEY = "nokware-voiced";
const TOKEN_BYTES = 24;

/** A random token in URL-safe base64 (32 characters for 24 bytes). */
export function makeToken(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

/** This browser's token, made on first use. Storage can be off (a private window): then a fresh one each time. */
export function deviceToken(): string {
  try {
    const kept = localStorage.getItem(TOKEN_KEY);
    if (kept) return kept;
    const made = makeToken(crypto.getRandomValues(new Uint8Array(TOKEN_BYTES)));
    localStorage.setItem(TOKEN_KEY, made);
    return made;
  } catch {
    return makeToken(crypto.getRandomValues(new Uint8Array(TOKEN_BYTES)));
  }
}

export function voicedIssues(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(VOICED_KEY) ?? "[]") as string[]);
  } catch {
    return new Set();
  }
}

export function rememberVoiced(publicId: string): void {
  try {
    localStorage.setItem(VOICED_KEY, JSON.stringify([...voicedIssues(), publicId]));
  } catch {
    // Storage off: the server still counts this browser's voice once.
  }
}

/** "14 residents say this affects them"; "No one has added their voice yet". */
export function voicesLine(count: number): string {
  if (count === 0) return "No one has added their voice yet";
  return `${count.toLocaleString()} ${count === 1 ? "resident says" : "residents say"} this affects them`;
}

/** For staff: "3 residents added their voice". */
export function voicesTally(count: number): string {
  return `${count.toLocaleString()} ${count === 1 ? "resident" : "residents"} added their voice`;
}
