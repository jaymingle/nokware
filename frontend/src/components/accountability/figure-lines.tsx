import type { ReactNode } from "react";

export type Line = { label: string; value: ReactNode; testId: string };

export function Lines({ title, lines, children }: { title: string; lines: Line[]; children?: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      <h3 className="text-[12.5px] font-medium tracking-wide text-ink-soft uppercase">{title}</h3>
      <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-4 gap-y-1 text-[13.5px]">
        {lines.map((line) => (
          <div key={line.label} className="contents" data-testid={line.testId}>
            <dt>{line.label}</dt>
            <dd className="text-right tabular-nums">{line.value}</dd>
          </div>
        ))}
      </dl>
      {children}
    </div>
  );
}
