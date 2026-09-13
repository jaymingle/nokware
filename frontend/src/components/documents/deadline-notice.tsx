"use client";

import { ClockIcon } from "lucide-react";

import { useNow } from "@/hooks/use-now";
import { cn } from "@/lib/utils";
import { deadlineFrom, formatDateTime } from "@/lib/time";

const TONE = {
  normal: "border-gold bg-gold-tint",
  urgent: "border-brick bg-brick-tint",
  passed: "border-hairline bg-paper-subtle",
} as const;

type DeadlineNoticeProps = {
  heldUntil: string;
  /** What stops publication, e.g. "you dispute it". */
  unless: string;
  size?: "lg" | "sm";
  testId?: string;
};

/**
 * The automatic-publication clock, stated as a consequence: "Publishes
 * automatically in 47h 12m unless you dispute it." Silence means publication,
 * so this is the most prominent thing on any document it applies to.
 */
export function DeadlineNotice({ heldUntil, unless, size = "lg", testId }: DeadlineNoticeProps) {
  const { label, urgency } = deadlineFrom(heldUntil, useNow());
  const large = size === "lg";
  return (
    <div
      data-testid={testId}
      data-urgency={urgency}
      className={cn("flex flex-wrap items-center gap-x-3 gap-y-1 border-l-[3px]", TONE[urgency], large ? "px-5 py-4" : "px-4 py-2.5")}
    >
      <ClockIcon aria-hidden className={cn("size-4 shrink-0", urgency === "urgent" ? "text-brick" : "text-gold")} />
      {urgency === "passed" ? (
        <p className={large ? "text-[15px]" : "text-[13.5px]"}>The clock has run out: this document is being published automatically.</p>
      ) : (
        <p className={large ? "text-[15px]" : "text-[13.5px]"}>
          Publishes automatically in{" "}
          <span
            className={cn(
              "font-heading leading-none tabular-nums",
              large ? "text-[26px]" : "text-[18px]",
              urgency === "urgent" && "text-brick",
            )}
          >
            {label}
          </span>{" "}
          unless {unless}.
        </p>
      )}
      <p className="text-[12.5px] text-ink-soft">
        {urgency === "urgent" ? "Final hours. " : ""}Deadline {formatDateTime(heldUntil)}
      </p>
    </div>
  );
}
