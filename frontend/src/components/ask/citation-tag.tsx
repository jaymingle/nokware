"use client";

import { isFigureLabel, labelNumber } from "@/lib/ask/figures";
import { cn } from "@/lib/utils";

export function CitationTag({ label, title, onCite, testId }: { label: string; title?: string; onCite: (label: string) => void; testId: string }) {
  const number = labelNumber(label);
  const figure = isFigureLabel(label);
  const kind = !figure ? "Source" : label.startsWith("B") ? "Budget figure" : "Live report figure";
  return (
    <button
      type="button"
      onClick={() => onCite(label)}
      aria-label={title ? `${kind} ${number}: ${title}` : `${kind} ${number}`}
      title={title}
      data-testid={testId}
      className={cn(
        "ml-0.5 inline-flex h-6 min-w-6 cursor-pointer items-center justify-center rounded-md px-1.5 align-[0.1em] text-[12px] leading-none font-medium tabular-nums transition-colors focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:outline-none",
        figure
          ? "bg-gold-tint text-ink hover:bg-gold hover:text-paper focus-visible:ring-gold"
          : "bg-teal-tint text-teal hover:bg-teal hover:text-paper focus-visible:ring-teal",
      )}
    >
      {figure ? `${label.replace(/\d+$/, "")}${number}` : number}
    </button>
  );
}
