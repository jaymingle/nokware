"use client";

import { useWidth } from "@/hooks/use-width";
import { SUPPRESSED_RANGE, chartScale, drawnValue, longMonth, monthLabel, shownRuns, spokenCount } from "@/lib/report/dashboard";

import type { MonthFigures } from "@/lib/api/types";

// Drawn at the width it is shown, so its labels stay 11px on a phone and a desktop.
const H = 250;
const PAD = { l: 34, r: 8, t: 12, b: 28 };
const INNER_H = H - PAD.t - PAD.b;
const FONT = 11;
const LABEL_ROOM = 30; // below this much room per month, every other month is labelled

function MonthsTable({ months }: { months: MonthFigures[] }) {
  return (
    <table className="sr-only">
      <caption>Reports received and resolved each month</caption>
      <thead>
        <tr><th scope="col">Month</th><th scope="col">Received</th><th scope="col">Resolved</th></tr>
      </thead>
      <tbody>
        {months.map((m) => (
          <tr key={m.month}><th scope="row">{longMonth(m.month)}</th><td>{spokenCount(m.received)}</td><td>{spokenCount(m.resolved)}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

function ResolvedMarks({ months, x, y }: { months: MonthFigures[]; x: (i: number) => number; y: (v: number) => number }) {
  const [low, high] = SUPPRESSED_RANGE;
  return months.map((m, i) => (m.resolved === null ? (
    <line key={m.month} x1={x(i)} x2={x(i)} y1={y(low)} y2={y(high)} className="stroke-teal" strokeWidth={1.5} strokeDasharray="3 2" />
  ) : (
    <circle key={m.month} cx={x(i)} cy={y(m.resolved)} r={2.5} className="fill-card stroke-teal" strokeWidth={1.5} />
  )));
}

export function TrendChart({ months }: { months: MonthFigures[] }) {
  const [box, W] = useWidth(600);
  const { max, ticks } = chartScale(months.flatMap((m) => [m.received, m.resolved]));
  const y = (v: number) => PAD.t + INNER_H - (v / max) * INNER_H;
  const step = (W - PAD.l - PAD.r) / Math.max(1, months.length);
  const barWidth = Math.min(24, step * 0.46);
  const x = (i: number) => PAD.l + step * i + step / 2;
  const labelled = (i: number) => step >= LABEL_ROOM || i % 2 === (months.length - 1) % 2; // the latest month always
  // The line breaks at a "fewer than 5" month rather than guess where it would be.
  const lines = shownRuns(months.map((m) => m.resolved)).map((run) => run.map((i) => `${x(i)},${y(months[i].resolved ?? 0)}`).join(" "));
  return (
    <div ref={box} data-testid="dashboard-trend">
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full font-sans" aria-hidden>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} className="stroke-hairline" strokeWidth={0.5} />
            <text x={PAD.l - 10} y={y(v) + 4} textAnchor="end" fontSize={FONT} className="fill-ink-soft tabular-nums">{v}</text>
          </g>
        ))}
        {months.map((m, i) => (
          <g key={m.month}>
            <rect x={x(i) - barWidth / 2} y={y(drawnValue(m.received))} width={barWidth} height={PAD.t + INNER_H - y(drawnValue(m.received))} rx={2}
              className={m.received === null ? "fill-none stroke-ink-muted" : "fill-hairline"} strokeDasharray={m.received === null ? "3 2" : undefined} />
            {labelled(i) ? <text x={x(i)} y={H - 8} textAnchor="middle" fontSize={FONT} className="fill-ink-soft">{monthLabel(m.month)}</text> : null}
          </g>
        ))}
        {lines.map((points) => (
          <polyline key={points} points={points} fill="none" className="stroke-teal" strokeWidth={1.5} strokeLinejoin="round" />
        ))}
        <ResolvedMarks months={months} x={x} y={y} />
      </svg>
      <MonthsTable months={months} />
    </div>
  );
}
