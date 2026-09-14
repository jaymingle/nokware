import { PhoneCallIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export function Note({ tone = "plain", children, testId }: { tone?: "plain" | "private"; children: ReactNode; testId?: string }) {
  return (
    <div
      className={cn(
        "rounded-xl px-4 py-3 text-[13px]",
        tone === "private" ? "bg-brick-tint text-brick" : "border text-ink-soft",
      )}
      data-testid={testId}
    >
      {children}
    </div>
  );
}

/** Nokware is not an emergency line; says so wherever someone may be in danger. */
export function EmergencyNote() {
  return (
    <p className="flex items-start gap-2.5 text-[13.5px] text-ink-soft">
      <PhoneCallIcon aria-hidden className="mt-0.5 size-4 shrink-0 text-brick" />
      <span>
        If someone is in danger right now, call <a href="tel:112" className="font-medium text-ink underline underline-offset-2" data-testid="report-call-112">112</a>,
        Ghana&apos;s emergency number. If it doesn&apos;t connect, try the Police on{" "}
        <a href="tel:191" className="font-medium text-ink underline underline-offset-2" data-testid="report-call-191">191</a> or{" "}
        <a href="tel:18555" className="font-medium text-ink underline underline-offset-2" data-testid="report-call-18555">18555</a>.
        Reports here are not watched around the clock.
      </span>
    </p>
  );
}
