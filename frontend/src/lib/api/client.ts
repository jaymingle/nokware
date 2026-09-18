import { AppwriteException } from "appwrite";

import { ApiError, UNREACHABLE, errorMessage } from "@/lib/api/errors";
import { timedOut, timedOutMessage, withTimeout } from "@/lib/api/timeout";
import { clearJwt, getJwt } from "@/lib/auth/jwt";
import { env } from "@/lib/env";

const SIGNED_OUT = "Your session has ended. Sign in again.";

async function bearer(): Promise<string> {
  try {
    return `Bearer ${await getJwt()}`;
  } catch (error) {
    if (error instanceof AppwriteException && error.code === 401) throw new ApiError(401, SIGNED_OUT);
    throw new ApiError(0, UNREACHABLE);
  }
}

async function send(path: string, init: RequestInit): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Authorization", await bearer());
  try {
    return await fetch(`${env.apiUrl}${path}`, withTimeout({ ...init, headers }));
  } catch (error) {
    throw new ApiError(0, timedOut(error) ? timedOutMessage(init) : UNREACHABLE);
  }
}

/** A 401 (e.g. a JWT revoked by signing out elsewhere) is retried once with a fresh JWT. */
export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response = await send(path, init);
  if (response.status === 401) {
    clearJwt();
    response = await send(path, init);
  }
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  return (await response.json()) as T;
}
