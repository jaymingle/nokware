// The recording goes to the API once and is never kept.
export const VOICE_MAX_SECONDS = 60;
export const MIC_BLOCKED = "Nokware can't hear you: the microphone is blocked. Allow it for this site in your browser, or type your question.";
export const NO_MIC = "No microphone was found. Type your question instead.";
export const MIC_FAILED = "The microphone couldn't be started. Type your question instead.";
export const VOICE_FAILED = "Your recording couldn't be read just now. Try again, or type your question.";

// Chrome and Firefox record WebM/Opus, Safari MP4/AAC; the API reads each.
const RECORDING_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

/** getUserMedia is missing on an insecure page. */
export function canRecord(): boolean {
  return typeof MediaRecorder !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia);
}

export function recordingType(): string | undefined {
  return RECORDING_TYPES.find((type) => MediaRecorder.isTypeSupported(type));
}

export function micProblem(error: unknown): string {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return MIC_BLOCKED;
  if (name === "NotFoundError" || name === "OverconstrainedError") return NO_MIC;
  return MIC_FAILED;
}

export function formatSeconds(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}
