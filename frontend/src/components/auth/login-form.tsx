"use client";

import { useEffect, useState, type ComponentProps, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuth } from "@/lib/auth/auth-context";
import { safeNext } from "@/lib/portal/navigation";

function Field({ id, label, ...input }: { id: string; label: string } & ComponentProps<typeof Input>) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} name={id} required {...input} />
    </div>
  );
}

export function LoginForm() {
  const { status, signIn } = useAuth();
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (status === "signed-in") router.replace(next);
  }, [status, next, router]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(null);
    setSubmitting(true);
    try {
      await signIn(String(form.get("email")), String(form.get("password")));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Sign-in failed. Try again.");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" data-testid="login-form">
      <Field id="email" label="Email" type="email" autoComplete="username" data-testid="login-email" />
      <Field id="password" label="Password" type="password" autoComplete="current-password" data-testid="login-password" />
      {error ? (
        <p role="alert" className="rounded-lg bg-brick-tint px-3 py-2.5 text-[13.5px] text-brick" data-testid="login-error">
          {error}
        </p>
      ) : null}
      <Button type="submit" disabled={submitting || status === "loading"} data-testid="login-submit">
        {submitting ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  );
}
