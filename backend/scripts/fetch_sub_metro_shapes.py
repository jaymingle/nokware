"""Fetch the three AMA sub-metro outlines from OpenStreetMap into the frontend's map data file.

    backend/.venv/bin/python backend/scripts/fetch_sub_metro_shapes.py

These are the only sub-metro polygons that exist anywhere public. AMA has not
published boundaries for its sub-metros or its electoral areas, and neither has
the Electoral Commission, the Ghana Statistical Service, HDX/OCHA, GADM or
GRID3 — their deepest Ghana boundary is the district, of which AMA is one. So
these outlines are an OpenStreetMap contributor's tracing from satellite
imagery, not an Assembly boundary, and the map that draws them says so.

The rings are simplified to about the detail a 700px-wide drawing can show, so
the file stays small enough to read in a diff. Nothing is smoothed or closed by
hand: a ring that does not close is an error, not something to patch.
"""

import json
import math
import urllib.request
from pathlib import Path
from typing import Any

OUT = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "map" / "sub-metros.json"
OSM_API = "https://api.openstreetmap.org/api/0.6/relation/{id}/full.json"
AGENT = "nokware-map-build/1.0 (civic transparency; contact via github.com/jaymingle/nokware)"
# id -> the sub-metro id Nokware uses, so the drawing joins to the figures by our own key, not by OSM's name.
RELATIONS = {20406318: "ashiedu-keteke", 20406317: "okaikoi-south", 20406319: "ablekuma-south"}
TOLERANCE = 0.00012  # degrees: about 13 metres, below what a 700px drawing of Accra can show


def fetch(relation_id: int) -> list[dict[str, Any]]:
    request = urllib.request.Request(OSM_API.format(id=relation_id), headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=120) as reply:
        return list(json.loads(reply.read())["elements"])


def rings(relation: dict[str, Any], ways: dict[int, list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """The relation's outer ways joined end to end into closed rings, in the order they connect."""
    pieces = [list(ways[member["ref"]]) for member in relation["members"]
              if member["type"] == "way" and member["role"] in ("outer", "") and member["ref"] in ways]
    built: list[list[tuple[float, float]]] = []
    while pieces:
        ring = pieces.pop(0)
        joined = True
        while joined and ring[0] != ring[-1]:
            joined = False
            for index, piece in enumerate(pieces):
                if piece[0] == ring[-1]:
                    ring += piece[1:]
                elif piece[-1] == ring[-1]:
                    ring += piece[-2::-1]
                elif piece[-1] == ring[0]:
                    ring = piece[:-1] + ring
                elif piece[0] == ring[0]:
                    ring = piece[:0:-1] + ring
                else:
                    continue
                pieces.pop(index)
                joined = True
                break
        built.append(ring)
    return built


def simplify(ring: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    """Ramer-Douglas-Peucker: drop the points a drawing this size cannot show."""
    if len(ring) < 3:
        return ring
    start, end = ring[0], ring[-1]
    furthest, distance = 0, 0.0
    for index, point in enumerate(ring[1:-1], start=1):
        gap = _from_line(point, start, end)
        if gap > distance:
            furthest, distance = index, gap
    if distance <= tolerance:
        return [start, end]
    return simplify(ring[:furthest + 1], tolerance)[:-1] + simplify(ring[furthest:], tolerance)


def _from_line(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    (x, y), (x1, y1), (x2, y2) = point, start, end
    run, rise = x2 - x1, y2 - y1
    if run == 0 and rise == 0:
        return math.hypot(x - x1, y - y1)
    along = max(0.0, min(1.0, ((x - x1) * run + (y - y1) * rise) / (run * run + rise * rise)))
    return math.hypot(x - (x1 + along * run), y - (y1 + along * rise))


def main() -> None:
    shapes = []
    for osm_id, our_id in RELATIONS.items():
        elements = fetch(osm_id)
        nodes = {e["id"]: (e["lon"], e["lat"]) for e in elements if e["type"] == "node"}
        ways = {e["id"]: [nodes[ref] for ref in e["nodes"] if ref in nodes] for e in elements if e["type"] == "way"}
        relation = next(e for e in elements if e["type"] == "relation" and e["id"] == osm_id)
        built = rings(relation, ways)
        open_rings = [ring for ring in built if ring[0] != ring[-1]]
        if open_rings:
            raise SystemExit(f"{relation['tags'].get('name')}: {len(open_rings)} ring(s) do not close; not writing")
        kept = [[[round(x, 5), round(y, 5)] for x, y in simplify(ring, TOLERANCE)] for ring in built]
        points_before = sum(len(ring) for ring in built)
        print(f"  {our_id:16} {relation['tags'].get('name','')[:34]:34} "
              f"{len(built)} ring(s), {points_before} points -> {sum(len(r) for r in kept)}")
        shapes.append({"id": our_id, "name": relation["tags"].get("short_name") or relation["tags"].get("name"),
                       "osm_relation": osm_id, "version": relation.get("version"), "rings": kept})

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": {
            "label": "OpenStreetMap contributors",
            "url": "https://www.openstreetmap.org/relation/20406318",
            "licence": "ODbL",
            "note": "The three AMA sub-metro outlines, traced from satellite imagery by an OpenStreetMap "
                    "contributor and tagged admin_level=7. AMA has not published boundaries for its sub-metros "
                    "or its electoral areas, and nor has the Electoral Commission, the Ghana Statistical "
                    "Service, HDX/OCHA, GADM or GRID3 — the deepest Ghana boundary any of them publishes is "
                    "the district, of which AMA is one. So this is the nearest thing that exists, not an "
                    "Assembly boundary, and the map says so wherever it is drawn.",
        },
        "fetched_by": "backend/scripts/fetch_sub_metro_shapes.py",
        "sub_metros": shapes,
    }, indent=1) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
