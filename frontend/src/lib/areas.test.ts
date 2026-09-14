import { describe, expect, it } from "vitest";

import { areaKey, matchAreas } from "@/lib/areas";

import type { SubMetroRepresentation } from "@/lib/api/types";

const subMetro = (name: string, areas: [string, string[]][]): SubMetroRepresentation => ({
  id: areaKey(name), name, chairperson: "Hon. A", chairperson_area: "X", office: "Y",
  electoral_areas: areas.map(([n, alternates]) => ({ id: areaKey(n), name: n, alternates })),
});

const SUB_METROS = [
  subMetro("Okaikoi South", [["Bubiashie", ["Bubuashie"]], ["Bubui", []], ["Kantesian", ["Kantsian"]]]),
  subMetro("Ablekuma South", [["Nmlitsa-Gonno", ["Nmlitsagonno"]]]),
];

describe("matchAreas", () => {
  it("finds an area by its name or any other spelling, ignoring case and punctuation", () => {
    expect(matchAreas("bubu", SUB_METROS).map((m) => m.area.name)).toEqual(["Bubiashie", "Bubui"]);
    expect(matchAreas("Bubuashie", SUB_METROS)).toMatchObject([{ area: { name: "Bubiashie" }, spelledAs: "Bubuashie" }]);
    expect(matchAreas("nmlitsa gonno", SUB_METROS)[0].subMetro.name).toBe("Ablekuma South");
  });

  it("lists every area, by name, when nothing is typed", () => {
    expect(matchAreas("", SUB_METROS).map((m) => m.area.name)).toEqual(["Bubiashie", "Bubui", "Kantesian", "Nmlitsa-Gonno"]);
    expect(matchAreas("Madina", SUB_METROS)).toEqual([]);
  });
});
