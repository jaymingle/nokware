"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { StatusScreen } from "@/components/portal/status-screen";
import { getFileLink } from "@/lib/api/endpoints";
import { useAuth } from "@/lib/auth/auth-context";

/**
 * Opens a document's PDF. File links are short-lived, so View PDF links here
 * (a plain link that pop-up blockers leave alone), and this page fetches a
 * fresh link as the signed-in user and replaces itself with the PDF.
 */
export function FileRedirect({ id }: { id: string }) {
  const { status } = useAuth();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (status !== "signed-in") return;
    getFileLink(id)
      .then(({ url }) => window.location.replace(url))
      .catch((failure: unknown) => setError(failure instanceof Error ? failure.message : "Couldn't open the PDF."));
  }, [id, status]);

  if (status === "signed-out" || status === "no-role") {
    return (
      <StatusScreen title="Sign in to view this PDF">
        <Link href="/login" className="text-sm text-teal underline underline-offset-2" data-testid="file-sign-in">
          Go to sign in
        </Link>
      </StatusScreen>
    );
  }
  if (error) {
    return (
      <StatusScreen title="Couldn't open the PDF">
        <p role="alert" className="text-sm text-ink-soft">
          {error}
        </p>
      </StatusScreen>
    );
  }
  return <StatusScreen title="Opening the PDF…" />;
}
