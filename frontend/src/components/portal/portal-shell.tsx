"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { PortalHeader } from "@/components/portal/portal-header";
import { StatusScreen } from "@/components/portal/status-screen";
import { SkipLink } from "@/components/skip-link";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth/auth-context";

function SignedOutRedirect() {
  const router = useRouter();
  const pathname = usePathname();
  useEffect(() => {
    router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [router, pathname]);
  return <StatusScreen title="Taking you to sign in…" />;
}

function NoAccess({ message, onSignOut }: { message: string; onSignOut: () => void }) {
  return (
    <StatusScreen title="No portal access">
      <p className="text-sm text-ink-soft">{message}</p>
      <div>
        <Button variant="secondary" onClick={onSignOut} data-testid="portal-no-access-sign-out">
          Sign out
        </Button>
      </div>
    </StatusScreen>
  );
}

function Unavailable({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <StatusScreen title="The portal is unavailable">
      <p className="text-sm text-ink-soft">{message}</p>
      <div>
        <Button onClick={onRetry} data-testid="portal-retry">
          Try again
        </Button>
      </div>
    </StatusScreen>
  );
}

/** Shows the portal only to a signed-in user with a role; handles every other state. */
export function PortalShell({ children }: { children: ReactNode }) {
  const { status, error, signOut, retry } = useAuth();
  if (status === "loading") return <StatusScreen title="Opening the portal…" />;
  if (status === "signed-out") return <SignedOutRedirect />;
  if (status === "no-role") return <NoAccess message={error ?? ""} onSignOut={() => void signOut()} />;
  if (status === "unavailable") return <Unavailable message={error ?? ""} onRetry={retry} />;
  return (
    <div className="relative flex flex-1 flex-col">
      <SkipLink />
      <PortalHeader />
      <main id="main" className="mx-auto w-full max-w-[1360px] flex-1 px-7 pt-9 pb-16">{children}</main>
    </div>
  );
}
