"use client";

import Link from "next/link";

import { CountValue } from "@/components/dashboard/count";
import { useSvgId } from "@/hooks/use-svg-id";
import { useWidth } from "@/hooks/use-width";
import { SUB_METRO_SHAPES, labelFor, pathFor, projection } from "@/lib/map/sub-metro-shapes";
import { spokenCount, type Count } from "@/lib/report/dashboard";
import { cn } from "@/lib/utils";

import type { ElectoralAreaFigures, SubMetroFigures } from "@/lib/api/types";

/*
 * The sub-metros have outlines (traced on OpenStreetMap, not published by AMA), so they are drawn. The electoral
 * areas have no published boundary anywhere, so they are tiles: a tile claims a name and a count, nothing about
 * where the area begins or ends.
 */

const HEIGHT = 340;
const SHADES = 4;
// A suppressed count is hatched, not shaded: a shade would place it on the scale, which is what suppressing it denies.
const HATCHED = "repeating-linear-gradient(45deg, var(--paper-raised) 0 4px, var(--teal-tint) 4px 8px)";

type Areas = { subMetros: SubMetroFigures[]; areas: ElectoralAreaFigures[] };

function step(count: Count, largest: number): number | null {
  if (count === null || count === 0) return null;
  return Math.max(1, Math.ceil((count / Math.max(largest, 1)) * SHADES));
}

// Stops short of full teal: ink on full teal is 2.6:1 and fails AA. Capped here, ink reads on every step at
// 12.2, 9.4, 7.2 and 5.5 to one, measured in sRGB.
const MIX = [18, 34, 50, 66];

function fill(step: number | null): string {
  if (step === null) return "var(--paper-raised)";
  return `color-mix(in srgb, var(--teal) ${MIX[step - 1]}%, var(--paper-raised))`;
}

function Hatch({ id }: { id: string }) {
  return (
    <defs>
      <pattern id={id} width={6} height={6} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width={6} height={6} fill="var(--paper-raised)" />
        <line x1={0} y1={0} x2={0} y2={6} strokeWidth={1.5} stroke="var(--teal)" opacity={0.55} />
      </pattern>
    </defs>
  );
}

function SubMetroMap({ subMetros }: { subMetros: SubMetroFigures[] }) {
  const [box, width] = useWidth(560);
  const hatch = useSvgId("hatch");
  const project = projection(width, HEIGHT);
  const font = width < 480 ? 10 : 12; // on a phone the shapes shrink but the type does not, so a name would run over its neighbour
  const byId = new Map(subMetros.map((row) => [row.id, row]));
  const largest = Math.max(0, ...subMetros.map((row) => row.reports ?? 0));
  return (
    <div ref={box} data-testid="areas-sub-metro-map">
      <svg viewBox={`0 0 ${width} ${HEIGHT}`} className="block h-auto w-full font-sans" aria-hidden>
        <Hatch id={hatch} />
        {SUB_METRO_SHAPES.map((shape) => {
          const figures = byId.get(shape.id);
          const count = figures ? figures.reports : 0;
          const shade = step(count, largest);
          const [x, y] = labelFor(shape, project);
          return (
            <g key={shape.id}>
              <path
                d={pathFor(shape, project)}
                fill={count === null ? `url(#${hatch})` : fill(shade)}
                stroke="var(--ink-soft)"
                strokeWidth={0.75}
              />
              <text x={x} y={y - 4} textAnchor="middle" fontSize={font} className="fill-ink">{figures?.name ?? shape.name}</text>
              <text x={x} y={y + font} textAnchor="middle" fontSize={font} className="fill-ink-soft tabular-nums">
                {spokenCount(count)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function AreaTile({ area, largest }: { area: ElectoralAreaFigures; largest: number }) {
  const suppressed = area.reports === null;
  const shade = step(area.reports, largest);
  return (
    <li
      className={cn(
        "flex min-w-0 flex-col gap-0.5 rounded-lg border px-2.5 py-2",
        suppressed && "border-teal/40",
      )}
      style={{ background: suppressed ? HATCHED : fill(shade) }}
      data-testid={`area-tile-${area.id}`}
    >
      <span className="truncate text-[12.5px] leading-tight text-ink" title={area.name}>{area.name}</span>
      <span className="text-[14px] font-medium text-ink tabular-nums">
        <CountValue value={area.reports} />
      </span>
    </li>
  );
}

function AreasTable({ subMetros, areas }: Areas) {
  return (
    <div className="sr-only">
      <table>
      <caption>Reports received and resolved in the last twelve months, by sub-metro and electoral area</caption>
      <thead>
        <tr><th scope="col">Sub-metro</th><th scope="col">Electoral area</th><th scope="col">Received</th><th scope="col">Resolved</th></tr>
      </thead>
      <tbody>
        {subMetros.map((subMetro) => (
          <tr key={subMetro.name}>
            <th scope="row">{subMetro.name}</th><td>All areas</td><td>{spokenCount(subMetro.reports)}</td><td>{spokenCount(subMetro.resolved)}</td>
          </tr>
        ))}
        {areas.map((area) => (
          <tr key={area.id}>
            <td>{subMetroName(subMetros, area)}</td><th scope="row">{area.name}</th>
            <td>{spokenCount(area.reports)}</td><td>{spokenCount(area.resolved)}</td>
          </tr>
        ))}
      </tbody>
    </table>
    </div>
  );
}

function subMetroName(subMetros: SubMetroFigures[], area: ElectoralAreaFigures): string {
  return subMetros.find((row) => row.id === area.sub_metro)?.name ?? area.sub_metro;
}

function WhyTiles() {
  return (
    <p className="max-w-[72ch] text-[12.5px] text-ink-soft" data-testid="areas-why-tiles">
      The electoral areas are tiles rather than shapes because nobody publishes their boundaries — not the Electoral
      Commission, the Ghana Statistical Service, HDX, GADM or GRID3, whose deepest boundary for Ghana is the district,
      of which Accra Metropolitan is one. Nokware could draw an approximate shape; it would be an invention, and a
      wrong line on a map is harder to doubt than an honest tile.{" "}
      <Link href="/accountability" className="text-teal underline underline-offset-2" data-testid="areas-finding-link">
        The record says where we looked.
      </Link>
    </p>
  );
}

export function AreasMap({ subMetros, areas }: Areas) {
  const largest = Math.max(0, ...areas.map((area) => area.reports ?? 0));
  const grouped = SUB_METRO_SHAPES.map((shape) => ({
    shape,
    name: subMetros.find((row) => row.id === shape.id)?.name ?? shape.name,
    here: areas.filter((area) => area.sub_metro === shape.id),
  }));
  return (
    <div className="flex flex-col gap-5" data-testid="areas-map">
      <SubMetroMap subMetros={subMetros} />
      <p className="text-[12px] text-ink-soft">
        Sub-metro outlines from{" "}
        <a href="https://www.openstreetmap.org/relation/20406318" target="_blank" rel="noopener"
          className="text-teal underline underline-offset-2" data-testid="areas-osm-link">OpenStreetMap contributors</a>{" "}
        (ODbL), traced from satellite imagery. AMA has published no boundary of its own, so these are the nearest
        thing that exists, not an Assembly boundary.
      </p>
      <div className="flex flex-col gap-3.5 border-t pt-4">
        {grouped.map(({ shape, name, here }) => (
          <div key={shape.id} className="flex flex-col gap-1.5">
            <h3 className="text-[12.5px] font-medium tracking-wide text-ink-soft uppercase">{name}</h3>
            <ul className="grid grid-cols-2 gap-1.5 sm:grid-cols-3 lg:grid-cols-4" data-testid={`area-tiles-${shape.id}`}>
              {here.map((area) => <AreaTile key={area.id} area={area} largest={largest} />)}
            </ul>
          </div>
        ))}
      </div>
      <WhyTiles />
      <AreasTable subMetros={subMetros} areas={areas} />
    </div>
  );
}
