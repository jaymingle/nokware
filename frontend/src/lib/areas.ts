import type { ElectoralArea, SubMetroRepresentation } from "@/lib/api/types";

export type AreaMatch = { area: ElectoralArea; subMetro: SubMetroRepresentation; spelledAs: string | null };

/** Letters and digits only, lower case: "Nmlitsa-Gonno" and "nmlitsagonno" compare equal. */
export function areaKey(text: string): string {
  return text.toLowerCase().replace(/[^a-z0-9]/g, "");
}

export function matchAreas(query: string, subMetros: SubMetroRepresentation[]): AreaMatch[] {
  const key = areaKey(query);
  const matches: AreaMatch[] = [];
  for (const subMetro of subMetros) {
    for (const area of subMetro.electoral_areas) {
      const alternate = area.alternates.find((a) => key && areaKey(a).includes(key));
      if (!key || areaKey(area.name).includes(key)) matches.push({ area, subMetro, spelledAs: null });
      else if (alternate) matches.push({ area, subMetro, spelledAs: alternate });
    }
  }
  return matches.sort((a, b) => a.area.name.localeCompare(b.area.name));
}
