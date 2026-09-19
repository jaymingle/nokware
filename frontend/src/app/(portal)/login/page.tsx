import { ArrowLeftIcon } from "lucide-react";
import Link from "next/link";
import { Suspense } from "react";

import { LoginForm } from "@/components/auth/login-form";
import { PageShell } from "@/components/page-shell";
import { Brand } from "@/components/portal/brand";
import { Card, CardContent } from "@/components/ui/card";

import type { Metadata } from "next";

export const metadata: Metadata = { title: "Sign in" };

// Sign-in carries no header of its own, so the gutter that the public and
// portal layouts supply is spent here instead.
export default function LoginPage() {
  return (
    <main id="main" className="flex w-full flex-1 flex-col px-5 sm:px-7">
      <PageShell
        eyebrow={
          <Link href="/" aria-label="Nokware home" data-touch-target className="inline-flex w-fit items-center" data-testid="login-home">
            <Brand />
          </Link>
        }
        title="Institution portal"
        lead={
          <>
            For Assembly departments, registered contributors and the MCE&apos;s office. Residents don&apos;t need an
            account: the Ledger and Ask are public.
          </>
        }
      >
        <Card>
          <CardContent>
            {/* useSearchParams (the ?next= destination) needs a Suspense boundary */}
            <Suspense>
              <LoginForm />
            </Suspense>
          </CardContent>
        </Card>
        {/* The logo above is a link, but nothing about a logo says so. Someone who lands here by mistake — most
            people who land here — needs a way out that reads as one. */}
        <Link href="/" data-touch-target
          className="inline-flex w-fit items-center gap-1.5 text-[14px] text-teal underline underline-offset-2"
          data-testid="login-public-site">
          <ArrowLeftIcon aria-hidden className="size-4" />
          Back to the public site
        </Link>
      </PageShell>
    </main>
  );
}
