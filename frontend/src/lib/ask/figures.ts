import type { AskFigure } from "@/lib/api/types";

export function isFigureLabel(label: string): boolean {
  return label.startsWith("R") || label.startsWith("B"); // R: a live count; B: an amount read from a budget
}

/** "R2" and "S2" both read 2, told apart by style. */
export function labelNumber(label: string): string {
  return label.replace(/^[SRB]/, "");
}

export function markFiguresCited(figures: AskFigure[], cited: string[]): AskFigure[] {
  const citedSet = new Set(cited);
  return figures.map((figure) => ({ ...figure, cited: citedSet.has(figure.label) }));
}

const countedFormat = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Africa/Accra",
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

export function countedAt(iso: string): string {
  return `Counted ${countedFormat.format(new Date(iso))} GMT`;
}
