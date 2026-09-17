import { describe, expect, it } from "vitest";

import { SUB_METRO_SHAPES, SUB_METRO_SOURCE, labelFor, pathFor, projection } from "@/lib/map/sub-metro-shapes";

const WIDTH = 560;
const HEIGHT = 340;

/** The test's own crossing rule, so the drawing isn't marking its own work. */
function encloses(ring: number[][], [x, y]: [number, number]): boolean {
  let within = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) within = !within;
  }
  return within;
}

describe("the sub-metro outlines", () => {
  it("are the three AMA sub-metros, each a closed ring", () => {
    expect(SUB_METRO_SHAPES.map((shape) => shape.id).sort()).toEqual(["ablekuma-south", "ashiedu-keteke", "okaikoi-south"]);
    for (const shape of SUB_METRO_SHAPES) {
      for (const ring of shape.rings) {
        expect(ring.length).toBeGreaterThan(3);
        expect(ring[0]).toEqual(ring[ring.length - 1]);
      }
    }
  });

  it("say where they come from, because they are not a boundary AMA published", () => {
    expect(SUB_METRO_SOURCE.label).toContain("OpenStreetMap");
    expect(SUB_METRO_SOURCE.licence).toBe("ODbL");
    expect(SUB_METRO_SOURCE.note).toMatch(/not an\s+Assembly boundary|not an Assembly boundary/);
  });

  it("sit over Accra, and inside the box they are drawn in", () => {
    for (const shape of SUB_METRO_SHAPES) {
      for (const [lon, lat] of shape.rings.flat()) {
        expect(lon).toBeGreaterThan(-0.3);
        expect(lon).toBeLessThan(-0.15);
        expect(lat).toBeGreaterThan(5.4);
        expect(lat).toBeLessThan(5.7);
      }
    }
    const project = projection(WIDTH, HEIGHT);
    for (const [x, y] of SUB_METRO_SHAPES.flatMap((shape) => shape.rings.flat()).map(project)) {
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(WIDTH);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(HEIGHT);
    }
  });

  it("put every label inside its own shape", () => {
    // The mean of a ring's points falls outside an L-shaped one: Ashiedu Keteke's label landed on its
    // neighbour, which says something false about where the reports are.
    const project = projection(WIDTH, HEIGHT);
    for (const shape of SUB_METRO_SHAPES) {
      const widest = shape.rings.reduce((a, b) => (b.length > a.length ? b : a)).map(project);
      expect(encloses(widest, labelFor(shape, project))).toBe(true);
    }
  });

  it("draw as a closed path per ring", () => {
    const project = projection(WIDTH, HEIGHT);
    for (const shape of SUB_METRO_SHAPES) {
      const path = pathFor(shape, project);
      expect(path.startsWith("M")).toBe(true);
      expect(path.match(/Z/g)).toHaveLength(shape.rings.length);
      expect(path).not.toContain("NaN");
    }
  });
});
