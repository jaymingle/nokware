export const UNREACHABLE = "Can't reach Nokware right now. Check your connection and try again.";

/** A failed API call. status 0 means the request never got a response. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    /** The request waited its whole deadline. Trying again would only spend the reader's patience twice over. */
    readonly ranOutOfTime = false,
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

/** The API's own words for a failure, to show as they are. */
export async function errorMessage(response: Response): Promise<string> {
  const body = (await response.json().catch(() => ({}))) as ErrorBody;
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) return body.detail.map(describeIssue).join("; ");
  return `Something went wrong (${response.status}). Try again.`;
}

const MAX_RETRIES = 2;

/**
 * Retry only when the service may recover (unreachable or a 5xx), never a refusal — and never a request that
 * already waited its whole deadline, which would leave the reader on a spinner for three deadlines instead of one
 * before the page could say anything at all.
 */
export function shouldRetry(failureCount: number, error: Error): boolean {
  if (error instanceof ApiError && error.ranOutOfTime) return false;
  const transient = !(error instanceof ApiError) || error.status === 0 || error.status >= 500;
  return transient && failureCount < MAX_RETRIES;
}
