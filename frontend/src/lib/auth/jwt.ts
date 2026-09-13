import { account } from "@/lib/appwrite";

const JWT_LIFETIME_MS = 15 * 60 * 1000; // Appwrite's default JWT lifetime
const REFRESH_MARGIN_MS = 60 * 1000; // mint a new one when less than this remains

type CachedJwt = { token: string; expiresAt: number };

let cached: CachedJwt | null = null;
let pending: Promise<string> | null = null;

async function mintJwt(): Promise<string> {
  const issuedAt = Date.now();
  const { jwt } = await account.createJWT();
  cached = { token: jwt, expiresAt: issuedAt + JWT_LIFETIME_MS };
  return jwt;
}

/**
 * A JWT for the signed-in Appwrite session, kept in memory only and reused
 * until shortly before it expires. Concurrent callers share one request.
 * Rejects with Appwrite's 401 when there is no session.
 */
export function getJwt(): Promise<string> {
  if (cached && cached.expiresAt - REFRESH_MARGIN_MS > Date.now()) {
    return Promise.resolve(cached.token);
  }
  pending ??= mintJwt().finally(() => {
    pending = null;
  });
  return pending;
}

export function clearJwt(): void {
  cached = null;
}
