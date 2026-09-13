import { chartScale, longMonth, monthLabel } from "@/lib/report/dashboard";

import type { MonthFigures } from "@/lib/api/types";

// The design's chart: received as bars, resolved in the month as a line.
const W = 720;
const H = 250;
const PAD = { l: 40, r: 8, t: 12, b: 28 };
const INNER_W = W - PAD.l - PAD.r;
const INNER_H = H - PAD.t - PAD.b;

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
  const { max, ticks } = chartScale(months.flatMap((m) => [m.received, m.resolved]));
  const y = (v: number) => PAD.t + INNER_H - (v / max) * INNER_H;
  const step = INNER_W / Math.max(1, months.length);
  const barWidth = Math.min(24, step * 0.46);
  const x = (i: number) => PAD.l + step * i + step / 2;
  const line = months.map((m, i) => `${x(i)},${y(m.resolved)}`).join(" ");
  return (
    <div data-testid="dashboard-trend">
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full font-sans" aria-hidden>
        {ticks.map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} className="stroke-hairline" strokeWidth={0.5} />
            <text x={PAD.l - 10} y={y(v) + 4} textAnchor="end" fontSize={10.5} className="fill-ink-soft tabular-nums">{v}</text>
          </g>
        ))}
        {months.map((m, i) => (
          <g key={m.month}>
            <rect x={x(i) - barWidth / 2} y={y(m.received)} width={barWidth} height={PAD.t + INNER_H - y(m.received)} rx={2} className="fill-hairline" />
            <text x={x(i)} y={H - 8} textAnchor="middle" fontSize={10.5} className="fill-ink-soft">{monthLabel(m.month)}</text>
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
