import { Brand } from "@/components/portal/brand";

import type { ReactNode } from "react";

/** A full-page message for states before the portal can render (loading, no access, outage). */
export function StatusScreen({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-6 px-6 py-16" aria-live="polite">
      <Brand />
      <div className="flex flex-col gap-3">
        <h1 className="text-[28px]">{title}</h1>
        {children}
      </div>
    </main>
  );
}
