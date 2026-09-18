import Link from "next/link";
import { Suspense } from "react";

import { LoginForm } from "@/components/auth/login-form";
import { Brand } from "@/components/portal/brand";
import { Card, CardContent } from "@/components/ui/card";

import type { Metadata } from "next";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-8 px-6 py-16">
      <Link href="/" aria-label="Nokware home" data-touch-target className="inline-flex w-fit items-center" data-testid="login-home">
        <Brand />
      </Link>
      <div className="flex flex-col gap-2">
        <h1 className="text-[34px] leading-tight">Institution portal</h1>
        <p className="text-sm text-ink-soft">
          For Assembly departments, registered contributors and the MCE&apos;s office. Residents don&apos;t need an
          account: the Ledger and Ask are public.
        </p>
      </div>
      <Card>
        <CardContent>
          {/* useSearchParams (the ?next= destination) needs a Suspense boundary */}
          <Suspense>
            <LoginForm />
          </Suspense>
        </CardContent>
      </Card>
    </main>
  );
}
