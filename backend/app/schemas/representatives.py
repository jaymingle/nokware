"""Who represents an electoral area: its sub-metro, the sub-metro's chairperson and office."""

from pydantic import BaseModel

from app.schemas.contacts import PublicContact


class ElectoralArea(BaseModel):
    id: str
    name: str
    alternates: list[str]  # other spellings in AMA's documents; a lookup matches any of them
    note: str | None = None


class SubMetroRepresentation(BaseModel):
    id: str
    name: str
    chairperson: str  # an elected Assembly Member, so named
    chairperson_area: str
    office: str
    electoral_areas: list[ElectoralArea]


class RepresentationSource(BaseModel):
    label: str
    url: str


class Representation(BaseModel):
    source: RepresentationSource
    switchboard: PublicContact  # no direct line for a sub-metro office is published
    sub_metros: list[SubMetroRepresentation]
    matched: str | None = None  # with ?area=, the electoral area it matched
