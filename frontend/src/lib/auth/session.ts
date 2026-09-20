import { AppwriteException } from "appwrite";

import { account } from "@/lib/appwrite";
import { clearJwt } from "@/lib/auth/jwt";

const ALREADY_SIGNED_IN = "user_session_already_exists";

/** A sign-in failure, with a message fit to show on the form. */
export class SignInError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SignInError";
  }
}

function signInMessage(error: unknown): string {
  if (!(error instanceof AppwriteException) || !error.code) {
    return "Can't reach the sign-in service. Check your connection and try again.";
  }
  if (error.code === 429) return "Too many attempts. Wait a minute, then try again.";
  if (error.type === "user_blocked") return "This account has been blocked. Contact the MCE's office.";
  if (error.code === 401 || error.code === 400) return "That email and password don't match a portal account.";
  return error.message;
}

export async function endSession(): Promise<void> {
  clearJwt();
  await account.deleteSession({ sessionId: "current" }).catch(() => undefined);
}

/** Replaces a session left over in this browser. Throws SignInError. */
export async function startSession(email: string, password: string): Promise<void> {
  const attempt = () => account.createEmailPasswordSession({ email, password });
  try {
    await attempt();
  } catch (error) {
    if (!(error instanceof AppwriteException) || error.type !== ALREADY_SIGNED_IN) {
      throw new SignInError(signInMessage(error));
    }
    await endSession();
    await attempt().catch((retryError: unknown) => {
      throw new SignInError(signInMessage(retryError));
    });
  }
  clearJwt();
}
