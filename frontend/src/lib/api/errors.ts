export const UNREACHABLE = "Can't reach Nokware right now. Check your connection and try again.";

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

/** The API's own words for a failure, to show as they are. */
export async function errorMessage(response: Response): Promise<string> {
  const body = (await response.json().catch(() => ({}))) as ErrorBody;
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) return body.detail.map(describeIssue).join("; ");
  return `Something went wrong (${response.status}). Try again.`;
}
