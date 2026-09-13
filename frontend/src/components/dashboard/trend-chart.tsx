"use client";

import { useEffect, useRef, useState, type RefObject } from "react";

import { chartScale, longMonth, monthLabel } from "@/lib/report/dashboard";

import type { MonthFigures } from "@/lib/api/types";

// The design's chart: received as bars, resolved in the month as a line. It is
// drawn at the width it is shown, so its labels stay 11px on a phone and a desktop.
const H = 250;
const PAD = { l: 34, r: 8, t: 12, b: 28 };
const INNER_H = H - PAD.t - PAD.b;
const FONT = 11;
const LABEL_ROOM = 30; // below this much room per month, every other month is labelled

function useWidth(fallback: number): [RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(240, Math.round(entry.contentRect.width))));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

function MonthsTable({ months }: { months: MonthFigures[] }) {
  return (
    <table className="sr-only">
      <caption>Reports received and resolved each month</caption>
      <thead>
        <tr><th scope="col">Month</th><th scope="col">Received</th><th scope="col">Resolved</th></tr>
      </thead>
      <tbody>
        {months.map((m) => (
          <tr key={m.month}><th scope="row">{longMonth(m.month)}</th><td>{m.received}</td><td>{m.resolved}</td></tr>
        ))}
      </tbody>
    </table>
  );
}

/** Twelve months of reports received (bars) and resolved (line), scaled to whole numbers. */
export function TrendChart({ months }: { months: MonthFigures[] }) {
  const [box, W] = useWidth(600);
  const { max, ticks } = chartScale(months.flatMap((m) => [m.received, m.resolved]));
  const y = (v: number) => PAD.t + INNER_H - (v / max) * INNER_H;
  const step = (W - PAD.l - PAD.r) / Math.max(1, months.length);
  const barWidth = Math.min(24, step * 0.46);
  const x = (i: number) => PAD.l + step * i + step / 2;
  const labelled = (i: number) => step >= LABEL_ROOM || i % 2 === (months.length - 1) % 2; // the latest month always
  const line = months.map((m, i) => `${x(i)},${y(m.resolved)}`).join(" ");
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
            <rect x={x(i) - barWidth / 2} y={y(m.received)} width={barWidth} height={PAD.t + INNER_H - y(m.received)} rx={2} className="fill-hairline" />
            {labelled(i) ? <text x={x(i)} y={H - 8} textAnchor="middle" fontSize={FONT} className="fill-ink-soft">{monthLabel(m.month)}</text> : null}
          </g>
        ))}
        <polyline points={line} fill="none" className="stroke-teal" strokeWidth={1.5} strokeLinejoin="round" />
        {months.map((m, i) => (
          <circle key={m.month} cx={x(i)} cy={y(m.resolved)} r={2.5} className="fill-card stroke-teal" strokeWidth={1.5} />
        ))}
      </svg>
      <MonthsTable months={months} />
    </div>
  );
}
