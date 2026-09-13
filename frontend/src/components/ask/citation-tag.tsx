"use client";

/** A citation in the answer, numbered like its source card; tapping it jumps to that card. */
export function CitationTag({ label, title, onCite, testId }: { label: string; title?: string; onCite: (label: string) => void; testId: string }) {
  const number = label.replace(/^S/, "");
  return (
    <button
      type="button"
      onClick={() => onCite(label)}
      aria-label={title ? `Source ${number}: ${title}` : `Source ${number}`}
      title={title}
      data-testid={testId}
      className="ml-0.5 inline-flex h-6 min-w-6 cursor-pointer items-center justify-center rounded-md bg-teal-tint px-1.5 align-[0.1em] text-[12px] leading-none font-medium text-teal tabular-nums transition-colors hover:bg-teal hover:text-paper focus-visible:ring-2 focus-visible:ring-teal focus-visible:ring-offset-1 focus-visible:outline-none"
    >
      {number}
    </button>
  );
}
