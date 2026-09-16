import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

export function LoadingPanel({ label }: { label: string }) {
  return (
    <Card>
      <CardContent className="text-sm text-ink-soft" aria-live="polite">
        {label}
      </CardContent>
    </Card>
  );
}

export function ErrorPanel({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center gap-4">
        <p role="alert" className="text-sm text-brick">
          {message}
        </p>
        <Button variant="secondary" size="sm" onClick={onRetry} data-testid="panel-retry">
          Try again
        </Button>
      </CardContent>
    </Card>
  );
}

export function EmptyPanel({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-1.5 py-4">
        <h2 className="text-[19px]">{title}</h2>
        {children ? <p className="max-w-[62ch] text-sm text-ink-soft">{children}</p> : null}
      </CardContent>
    </Card>
  );
}

/** An inline failure message inside a form or dialog. */
export function ErrorNote({ children, testId }: { children: ReactNode; testId?: string }) {
  return (
    <p role="alert" className="rounded-lg bg-brick-tint px-3 py-2.5 text-[13.5px] text-brick" data-testid={testId}>
      {children}
    </p>
  );
}
