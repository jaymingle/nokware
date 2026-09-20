// fetch() can't say how much of an upload has gone, and on a mobile connection the upload IS the wait: a resident
// who sees nothing move can't tell a slow photo from a report that failed. XMLHttpRequest still reports progress,
// so it is used for the one request that carries photos.
import { ApiError, UNREACHABLE } from "@/lib/api/errors";
import { TIMED_OUT_SENDING, UPLOAD_MS } from "@/lib/api/timeout";
import { env } from "@/lib/env";

/** How far the photos have gone, then what happens once they are all there. */
export type Sending = { sent: number; total: number } | "filing";

function failure(status: number, body: string): ApiError {
  try {
    const detail = (JSON.parse(body) as { detail?: unknown }).detail;
    if (typeof detail === "string") return new ApiError(status, detail);
    if (Array.isArray(detail)) return new ApiError(status, detail.map((issue) => String((issue as { msg?: string }).msg)).join("; "));
  } catch {
    // not JSON: the status is all there is to go on
  }
  return new ApiError(status, `Something went wrong (${status}). Try again.`);
}

export function postWithProgress<T>(path: string, form: FormData, onProgress: (sending: Sending) => void,
                                    headers: Record<string, string> = {}): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", `${env.apiUrl}${path}`);
    request.timeout = UPLOAD_MS;
    // A petition carries the proof of its creator's phone; a report carries nothing. Never Content-Type: the
    // browser sets it, with the multipart boundary only it knows.
    for (const [name, value] of Object.entries(headers)) request.setRequestHeader(name, value);
    request.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      // The last byte sent is not the answer: the API still has to read the report and route it.
      onProgress(event.loaded >= event.total ? "filing" : { sent: event.loaded, total: event.total });
    };
    request.upload.onload = () => onProgress("filing");
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        try {
          resolve(JSON.parse(request.responseText) as T);
        } catch {
          reject(new ApiError(request.status, "Nokware's answer couldn't be read. Check with your reference before sending it again."));
        }
      } else reject(failure(request.status, request.responseText));
    };
    request.onerror = () => reject(new ApiError(0, UNREACHABLE));
    request.ontimeout = () => reject(new ApiError(0, TIMED_OUT_SENDING));
    request.send(form);
  });
}
