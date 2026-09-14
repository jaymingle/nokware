"""Who represents you: an electoral area's sub-metro, chairperson and office. No sign-in.

    GET /api/representatives              every sub-metro and its electoral areas
    GET /api/representatives?area=Bubuashie   the one sub-metro for an area, by any of its spellings
"""

from fastapi import APIRouter, HTTPException

from app import contacts
from app.schemas.representatives import ElectoralArea, Representation, RepresentationSource, SubMetroRepresentation
from app.wards import SubMetro, Ward, find_ward, source, sub_metros, wards

router = APIRouter(prefix="/api/representatives", tags=["representatives"])
SWITCHBOARD = "ama-general"


def _area(ward: Ward) -> ElectoralArea:
    return ElectoralArea(id=ward.id, name=ward.name, alternates=list(ward.alternates), note=ward.note)


def _sub_metro(sub_metro: SubMetro, areas: list[Ward]) -> SubMetroRepresentation:
    return SubMetroRepresentation(
        id=sub_metro.id,
        name=sub_metro.name,
        chairperson=sub_metro.chairperson,
        chairperson_area=sub_metro.chairperson_area,
        office=sub_metro.office,
        electoral_areas=[_area(w) for w in areas],
    )


@router.get("", response_model=Representation)
def representatives(area: str | None = None) -> Representation:
    found = find_ward(area) if area else None
    if area and found is None:
        raise HTTPException(404, "No electoral area by that name. Check the spelling, or choose from the list.")
    chosen = [s for s in sub_metros().values() if found is None or s.id == found.sub_metro]
    listed = [
        _sub_metro(s, [w for w in wards().values() if w.sub_metro == s.id and (found is None or w.id == found.id)])
        for s in chosen
    ]
    return Representation(
        source=RepresentationSource(**source()),
        switchboard=contacts.contacts()[SWITCHBOARD],
        sub_metros=listed,
        matched=found.id if found else None,
    )
