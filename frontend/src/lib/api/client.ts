import { AppwriteException } from "appwrite";

import { clearJwt, getJwt } from "@/lib/auth/jwt";
import { env } from "@/lib/env";

const UNREACHABLE = "Can't reach Nokware right now. Check your connection and try again.";
const SIGNED_OUT = "Your session has ended. Sign in again.";

/** A failed API call. status 0 means the request never got a response. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type ValidationIssue = { loc: (string | number)[]; msg: string };
type ErrorBody = { detail?: string | ValidationIssue[] };

function describeIssue(issue: ValidationIssue): string {
  const field = issue.loc.filter((part) => part !== "body").join(".");
  return field ? `${field.replaceAll("_", " ")}: ${issue.msg}` : issue.msg;
}

async function errorMessage(response: Response): Promise<string> {
  const body = (await response.json().catch(() => ({}))) as ErrorBody;
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) return body.detail.map(describeIssue).join("; ");
  return `Something went wrong (${response.status}). Try again.`;
}

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
    return await fetch(`${env.apiUrl}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, UNREACHABLE);
  }
}

/**
 * Call the Nokware API as the signed-in user. A 401 (e.g. a JWT revoked by
 * signing out elsewhere) is retried once with a fresh JWT before giving up.
 */
export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response = await send(path, init);
  if (response.status === 401) {
    clearJwt();
    response = await send(path, init);
  }
  if (!response.ok) throw new ApiError(response.status, await errorMessage(response));
  return (await response.json()) as T;
}
