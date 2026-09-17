"use client";

import { useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";
import { createContext, use, useCallback, useMemo, type ReactNode } from "react";

import { getMe } from "@/lib/api/endpoints";
import { ApiError } from "@/lib/api/errors";
import { endSession, SignInError, startSession } from "@/lib/auth/session";

import type { Me } from "@/lib/api/types";

const ME_QUERY_KEY = ["me"] as const;

export type AuthStatus = "loading" | "signed-out" | "signed-in" | "no-role" | "unavailable";

type AuthContextValue = {
  status: AuthStatus;
  me: Me | null;
  error: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  retry: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

/** The signed-in user, or null when there is no Appwrite session. */
async function loadMe(): Promise<Me | null> {
  try {
    return await getMe();
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

type MeQuery = Pick<UseQueryResult<Me | null>, "isPending" | "error" | "data">;

function describe({ isPending, error, data }: MeQuery): Pick<AuthContextValue, "status" | "me" | "error"> {
  if (isPending) return { status: "loading", me: null, error: null };
  if (error) {
    const noRole = error instanceof ApiError && error.status === 403;
    return { status: noRole ? "no-role" : "unavailable", me: null, error: error.message };
  }
  return data ? { status: "signed-in", me: data, error: null } : { status: "signed-out", me: null, error: null };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const { isPending, error, data, refetch } = useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: loadMe,
    retry: false,
    staleTime: Infinity,
  });

  const signIn = useCallback(
    async (email: string, password: string) => {
      await startSession(email, password);
      const me = await getMe().catch(async (error: unknown) => {
        await endSession(); // a session without a portal role is no use here
        throw new SignInError(error instanceof Error ? error.message : "Sign-in failed. Try again.");
      });
      queryClient.setQueryData(ME_QUERY_KEY, me);
    },
    [queryClient],
  );

  const signOut = useCallback(async () => {
    await endSession();
    // Drop the previous user's data, but keep the "me" query itself: clearing it
    // would detach the mounted observer, so the portal would not see the sign-out.
    queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== ME_QUERY_KEY[0] });
    queryClient.setQueryData(ME_QUERY_KEY, null);
  }, [queryClient]);

  const value = useMemo(
    () => ({ ...describe({ isPending, error, data }), signIn, signOut, retry: () => void refetch() }),
    [isPending, error, data, signIn, signOut, refetch],
  );
  return <AuthContext value={value}>{children}</AuthContext>;
}

export function useAuth(): AuthContextValue {
  const value = use(AuthContext);
  if (!value) throw new Error("useAuth must be used inside <AuthProvider>");
  return value;
}

/** The signed-in user, for components rendered only inside the portal shell. */
export function useMe(): Me {
  const { me } = useAuth();
  if (!me) throw new Error("useMe needs a signed-in user; render it inside <PortalShell>");
  return me;
}
