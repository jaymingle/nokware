"use client";

import { useId } from "react";

import { useWidth } from "@/hooks/use-width";
import { RANGE_KEY, arcPath, barPieces, colour, exactRuns, hasRange, isRange, short, slices, tickLabel, type BarPiece } from "@/lib/ask/chart";
import { countedAt } from "@/lib/ask/figures";

import type { AskChart } from "@/lib/api/types";

// A chart the question asked for, of the answer's cited live figures. The API
// chose the kind (never one that can't show "fewer than 5" honestly) and the
// values; this draws them: an exact count as a bar or a point, "fewer than 5"
// as a hatched range from 1 to 4 or a dashed span. Drawn at the width it is
// shown, like the dashboard's chart, with the numbers in a table for screen readers.

const FONT = 11; // the smallest, on a phone
// A chart drawn 1,100px wide was still labelling itself at 11px, which reads as
// a thumbnail of a chart rather than the chart. The type grows with the drawing.
function fontFor(width: number): number {
  return width >= 620 ? 13 : width >= 440 ? 12 : FONT;
}
const PAD = { l: 34, r: 12, t: 16, b: 34 };
const MAX_BAR = 56; // pixels: a bar never grows into a slab
const CHAR = 0.56; // of the font size: enough to size a label column from the text

/** As much of a name as fits the space, ending in an ellipsis; the full name is in the table for screen readers. */
function fit(name: string, space: number, size: number = FONT): string {
  const room = Math.floor(space / (size * CHAR));
  return name.length <= room ? name : `${name.slice(0, Math.max(1, room - 1))}…`;
}

type Draw = { chart: AskChart; width: number; hatch: string };

/** Where a count sits along the value axis, in pixels from `start` towards `end`. */
function scale(chart: AskChart, start: number, end: number): (value: number) => number {
  return (value) => start + ((end - start) * value) / Math.max(1, chart.axis_max);
}

/** One hatching per series, in its colour: a pattern takes its colour where it is defined, not where it is used. */
function Hatches({ chart, id }: { chart: AskChart; id: string }) {
  return (
    <defs>
      {chart.series.map((series, i) => (
        <pattern key={series.name} id={`${id}-${i}`} width={6} height={6} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <line x1={0} y1={0} x2={0} y2={6} strokeWidth={1.5} style={{ stroke: colour(i) }} />
        </pattern>
      ))}
    </defs>
  );
}

function Piece({ piece, x, y, w, h, hatch }: { piece: BarPiece; x: number; y: number; w: number; h: number; hatch: string }) {
  if (w <= 0 || h <= 0) return null;
  const fill = colour(piece.series);
  if (!isRange(piece.value)) return <rect x={x} y={y} width={w} height={h} rx={2} style={{ fill }} />;
  return (
    <g style={{ color: fill }}>
      <rect x={x} y={y} width={w} height={h} fill={`url(#${hatch}-${piece.series})`} />
      <rect x={x} y={y} width={w} height={h} fill="none" stroke="currentColor" strokeWidth={1.2} strokeDasharray="3 2" />
    </g>
  );
}

function UprightBars({ chart, width, hatch }: Draw) {
  const font = fontFor(width);
  const height = 240;
  const y = scale(chart, height - PAD.b, PAD.t);
  const band = (width - PAD.l - PAD.r) / chart.categories.length;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="block h-auto w-full font-sans" aria-hidden>
      <Hatches chart={chart} id={hatch} />
      {chart.ticks.map((tick) => (
        <g key={tick}>
          <line x1={PAD.l} x2={width - PAD.r} y1={y(tick)} y2={y(tick)} className="stroke-hairline" strokeWidth={0.5} />
          <text x={PAD.l - 8} y={y(tick) + 4} textAnchor="end" fontSize={font} className="fill-ink-soft tabular-nums">{tickLabel(tick)}</text>
        </g>
      ))}
      {barPieces(chart, band, MAX_BAR).map((piece) => {
        const x = PAD.l + band * (piece.category + piece.offset);
        const w = band * piece.thickness - 2;
        return (
          <g key={`${piece.category}-${piece.series}`}>
            <Piece piece={piece} x={x} y={y(piece.to)} w={w} h={y(piece.from) - y(piece.to)} hatch={hatch} />
            {chart.kind === "stacked_bar" ? null : (
              <text x={x + w / 2} y={y(piece.to) - 4} textAnchor="middle" fontSize={font - 1} className="fill-ink-soft tabular-nums">{short(piece.value)}</text>
            )}
          </g>
        );
      })}
      {chart.categories.map((name, i) => (
        <text key={name} x={PAD.l + band * (i + 0.5)} y={height - 14} textAnchor="middle" fontSize={font} className="fill-ink-soft">{name}</text>
      ))}
    </svg>
  );
}

function FlatBars({ chart, width, hatch }: Draw) {
  const font = fontFor(width);
  const row = chart.kind === "stacked_bar" || chart.series.length === 1 ? Math.max(30, font * 2.4) : (font + 5) * chart.series.length + 12;
  const label = Math.min(width * 0.42, 8 + font * CHAR * Math.max(...chart.categories.map((c) => c.length)));
  const height = PAD.t + row * chart.categories.length + 22;
  // Room at the right for the longest value, so a figure never runs off the edge.
  const values = barPieces(chart, row, MAX_BAR / 2).map((piece) => short(piece.value).length);
  const x = scale(chart, label + 8, width - PAD.r - (8 + (font - 1) * CHAR * Math.max(...values, 2)));
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="block h-auto w-full font-sans" aria-hidden>
      <Hatches chart={chart} id={hatch} />
      {chart.ticks.map((tick) => (
        <g key={tick}>
          <line x1={x(tick)} x2={x(tick)} y1={PAD.t} y2={height - 22} className="stroke-hairline" strokeWidth={0.5} />
          <text x={x(tick)} y={height - 6} textAnchor="middle" fontSize={font} className="fill-ink-soft tabular-nums">{tickLabel(tick)}</text>
        </g>
      ))}
      {chart.categories.map((name, i) => (
        <text key={name} x={label} y={PAD.t + row * (i + 0.5) + 4} textAnchor="end" fontSize={font} className="fill-ink">{fit(name, label - 6, font)}</text>
      ))}
      {barPieces(chart, row, MAX_BAR / 2).map((piece) => {
        const y = PAD.t + row * (piece.category + piece.offset);
        const h = row * piece.thickness - 2;
        return (
          <g key={`${piece.category}-${piece.series}`}>
            <Piece piece={piece} x={x(piece.from)} y={y} w={x(piece.to) - x(piece.from)} h={h} hatch={hatch} />
            {chart.kind === "stacked_bar" ? null : (
              <text x={x(piece.to) + 4} y={y + h / 2 + 4} fontSize={font - 1} className="fill-ink-soft tabular-nums">{short(piece.value)}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function Line({ chart, width }: Draw) {
  const font = fontFor(width);
  const height = 240;
  const y = scale(chart, height - PAD.b, PAD.t);
  const step = (width - PAD.l - PAD.r) / chart.categories.length;
  const x = (i: number) => PAD.l + step * (i + 0.5);
  const every = Math.max(1, Math.ceil((chart.categories.length * 52) / (width - PAD.l - PAD.r)));
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="block h-auto w-full font-sans" aria-hidden>
      {chart.ticks.map((tick) => (
        <g key={tick}>
          <line x1={PAD.l} x2={width - PAD.r} y1={y(tick)} y2={y(tick)} className="stroke-hairline" strokeWidth={0.5} />
          <text x={PAD.l - 8} y={y(tick) + 4} textAnchor="end" fontSize={font} className="fill-ink-soft tabular-nums">{tickLabel(tick)}</text>
        </g>
      ))}
      {chart.series.map((series, s) => (
        <g key={series.name} style={{ color: colour(s) }}>
          {exactRuns(series.values).map((run) => (
            <polyline key={run[0]} points={run.map((i) => `${x(i)},${y(series.values[i].high)}`).join(" ")} fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinejoin="round" />
          ))}
          {series.values.map((value, i) => (isRange(value) ? (
            <line key={i} x1={x(i)} x2={x(i)} y1={y(value.low)} y2={y(value.high)} stroke="currentColor" strokeWidth={1.8} strokeDasharray="3 2" />
          ) : (
            <circle key={i} cx={x(i)} cy={y(value.high)} r={2.8} className="fill-card" stroke="currentColor" strokeWidth={1.5} />
          )))}
        </g>
      ))}
      {chart.categories.map((name, i) => (i % every === 0 || i === chart.categories.length - 1 ? (
        <text key={name} x={x(i)} y={height - 14} textAnchor="middle" fontSize={font} className="fill-ink-soft">{name}</text>
      ) : null))}
    </svg>
  );
}

function Pie({ chart }: Draw) {
  const size = 200;
  const inner = chart.kind === "donut" ? size * 0.27 : 0;
  const parts = slices(chart);
  return (
    <div className="flex flex-wrap items-center gap-5">
      <svg viewBox={`0 0 ${size} ${size}`} className="block size-[180px] shrink-0" aria-hidden>
        {parts.map((part, i) => (part.end > part.start ? (
          <path key={chart.categories[i]} d={arcPath(size / 2, size / 2, size / 2 - 2, inner, part.start, part.end)} style={{ fill: colour(i) }} className="stroke-card" strokeWidth={1.5} />
        ) : null))}
      </svg>
      <ul className="flex flex-col gap-1.5 text-[13px]">
        {chart.categories.map((name, i) => (
          <li key={name} className="flex items-center gap-2">
            <span aria-hidden className="size-3 shrink-0 rounded-sm" style={{ background: colour(i) }} />
            {name}: <span className="tabular-nums">{chart.series[0].values[i].shown}</span> <span className="text-ink-soft">({parts[i].share}%)</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Legend({ chart }: { chart: AskChart }) {
  if (chart.series.length < 2) return null;
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[12.5px]">
      {chart.series.map((series, i) => (
        <li key={series.name} className="flex items-center gap-1.5">
          <span aria-hidden className="size-3 rounded-sm" style={{ background: colour(i) }} />
          {series.name}
        </li>
      ))}
    </ul>
  );
}

/** The chart's numbers for screen readers, "fewer than 5" in words. */
function ChartTable({ chart }: { chart: AskChart }) {
  return (
    <table className="sr-only">
      <caption>{chart.title}</caption>
      <thead>
        <tr><th scope="col">{chart.over_time ? "Month" : "Category"}</th>{chart.series.map((s) => <th key={s.name} scope="col">{s.name}</th>)}</tr>
      </thead>
      <tbody>
        {chart.categories.map((name, i) => (
          <tr key={name}><th scope="row">{name}</th>{chart.series.map((s) => <td key={s.name}>{s.values[i].shown}</td>)}</tr>
        ))}
      </tbody>
    </table>
  );
}

function Drawing(props: Draw) {
  if (props.chart.kind === "pie" || props.chart.kind === "donut") return <Pie {...props} />;
  if (props.chart.kind === "line") return <Line {...props} />;
  return props.chart.horizontal ? <FlatBars {...props} /> : <UprightBars {...props} />;
}

export function AnswerChart({ chart, testId }: { chart: AskChart; testId: string }) {
  const [box, width] = useWidth(640);
  const hatch = `hatch-${useId().replace(/[^a-zA-Z0-9-]/g, "")}`;
  return (
    <figure className="flex flex-col gap-3 rounded-lg border bg-card p-3.5 sm:p-4" data-testid={`${testId}-chart`} data-kind={chart.kind}>
      <figcaption className="text-[15px] font-medium">{chart.title}</figcaption>
      {chart.note ? <p className="text-[13px] text-ink-soft italic" data-testid={`${testId}-chart-note`}>{chart.note}</p> : null}
      <Legend chart={chart} />
      <div ref={box}>
        <Drawing chart={chart} width={width} hatch={hatch} />
      </div>
      <p className="text-[12px] text-ink-soft">
        {chart.source === "documents"
          ? "Drawn from figures read from the documents cited, each one checked against the document it comes from; Nokware charts none it cannot check."
          : `Live report data. ${countedAt(chart.counted_at ?? "")}.${hasRange(chart) ? ` ${RANGE_KEY}` : ""}`}
      </p>
      <ChartTable chart={chart} />
    </figure>
  );
}
