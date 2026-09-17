import shapes from "@/lib/map/sub-metros.json";

/**
 * These are the only sub-metro polygons that exist publicly, and they are an
 * OpenStreetMap contributor's tracing, not a boundary the Assembly published,
 * so every drawing repeats the source note in sub-metros.json. The 20 electoral
 * areas have no polygons at all, which is why they are drawn as tiles.
 */

type SubMetroShape = { id: string; name: string; osm_relation: number; rings: number[][][] };

export const SUB_METRO_SOURCE = shapes.source;
export const SUB_METRO_SHAPES = shapes.sub_metros as SubMetroShape[];

const PAD = 4; // room for the stroke, which is centred on the edge

type Box = { west: number; east: number; south: number; north: number };

function bounds(): Box {
  const points = SUB_METRO_SHAPES.flatMap((shape) => shape.rings.flat());
  const lon = points.map(([x]) => x);
  const lat = points.map(([, y]) => y);
  return { west: Math.min(...lon), east: Math.max(...lon), south: Math.min(...lat), north: Math.max(...lat) };
}

/**
 * Equirectangular, with longitude squeezed by cos(latitude) so the city isn't
 * stretched sideways. At Accra's size the difference from a proper projection
 * is far under a pixel, and nothing here is measured off the drawing.
 */
export function projection(width: number, height: number) {
  const box = bounds();
  const squeeze = Math.cos(((box.north + box.south) / 2) * (Math.PI / 180));
  const spanX = (box.east - box.west) * squeeze;
  const spanY = box.north - box.south;
  const scale = Math.min((width - PAD * 2) / spanX, (height - PAD * 2) / spanY);
  const offsetX = (width - spanX * scale) / 2;
  const offsetY = (height - spanY * scale) / 2;
  return ([lon, lat]: number[]): [number, number] => [
    offsetX + (lon - box.west) * squeeze * scale,
    offsetY + (box.north - lat) * scale, // south is down
  ];
}

export function pathFor(shape: SubMetroShape, project: (point: number[]) => [number, number]): string {
  return shape.rings
    .map((ring) => ring.map((point, i) => `${i === 0 ? "M" : "L"}${project(point).map((n) => n.toFixed(1)).join(",")}`).join("") + "Z")
    .join(" ");
}

const GRID = 28; // samples across the shape's box; enough to place a label on shapes this simple

function inside([x, y]: [number, number], ring: [number, number][]): boolean {
  let within = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) within = !within;
  }
  return within;
}

function toEdge([x, y]: [number, number], ring: [number, number][]): number {
  let nearest = Infinity;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    const run = xj - xi;
    const rise = yj - yi;
    const along = run || rise ? Math.max(0, Math.min(1, ((x - xi) * run + (y - yi) * rise) / (run * run + rise * rise))) : 0;
    nearest = Math.min(nearest, Math.hypot(x - (xi + along * run), y - (yi + along * rise)));
  }
  return nearest;
}

/**
 * The point furthest from any edge, not the average of the ring's points: that
 * falls outside an L-shaped ring (Ashiedu Keteke's label landed on its
 * neighbour), and a label on the wrong shape misplaces the reports.
 */
export function labelFor(shape: SubMetroShape, project: (point: number[]) => [number, number]): [number, number] {
  const ring = shape.rings.reduce((widest, next) => (next.length > widest.length ? next : widest)).map(project);
  const xs = ring.map(([x]) => x);
  const ys = ring.map(([, y]) => y);
  const [left, right, top, bottom] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  let best: [number, number] = [(left + right) / 2, (top + bottom) / 2];
  let room = -1;
  for (let i = 1; i < GRID; i += 1) {
    for (let j = 1; j < GRID; j += 1) {
      const point: [number, number] = [left + ((right - left) * i) / GRID, top + ((bottom - top) * j) / GRID];
      if (!inside(point, ring)) continue;
      const gap = toEdge(point, ring);
      if (gap > room) [best, room] = [point, gap];
    }
  }
  return best;
}
