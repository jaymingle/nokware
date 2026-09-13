"""What a citizen report is about, and who receives it.

The classifier (or, for personal safety, the citizen) chooses one topic from
this fixed list; it never chooses a recipient. Each topic's recipients are set
in TOPICS below, one table the Assembly can read and change in one place.

This routing is a first draft for AMA to review, not AMA policy.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.teams import RECIPIENT_NAMES


class Category(StrEnum):
    CIVIC_SERVICE = "civic_service"
    PUBLIC_SAFETY = "public_safety"
    PERSONAL_SAFETY = "personal_safety"  # abuse or a threat to someone's life: private, always severity 5


POLICE = "agency-police"
GNFS = "agency-gnfs"
SOCIAL_WELFARE = "dept-social-welfare"
TRIAGE = "dept-central-administration"  # topic unclear, or classification failed


@dataclass(frozen=True)
class Topic:
    id: str
    category: Category
    label: str  # as shown to staff and, for civic and public safety, on the public dashboard
    guide: str  # what belongs here, for the classifier (or, for personal safety, the citizen)
    recipients: tuple[str, ...]

    @property
    def private(self) -> bool:
        return self.category == Category.PERSONAL_SAFETY


TOPICS: tuple[Topic, ...] = (
    # Civic service: a department's everyday responsibilities.
    Topic("solid_waste", Category.CIVIC_SERVICE, "Solid waste and dumping",
          "Uncollected refuse, overflowing bins, illegal dumping, burning rubbish.", ("dept-waste-management",)),
    Topic("drainage", Category.CIVIC_SERVICE, "Drainage and flooding",
          "Choked or broken drains and gutters, standing water, drains needing desilting.", ("dept-works",)),
    Topic("roads", Category.CIVIC_SERVICE, "Roads and potholes",
          "Potholes, damaged roads, pavements or bridges, missing road markings.", ("dept-urban-roads",)),
    Topic("street_lighting", Category.CIVIC_SERVICE, "Street lighting",
          "Streetlights that are out, flickering or missing.", ("dept-works",)),
    Topic("sanitation_facilities", Category.CIVIC_SERVICE, "Sanitation facilities",
          "Public toilets and urinals: closed, broken, unclean or missing.", ("dept-waste-management",)),
    Topic("public_health", Category.CIVIC_SERVICE, "Public health and hygiene",
          "Environmental health and sanitation inspection, food hygiene and unhygienic vending, mosquito breeding "
          "sites, dead animals, public health nuisances.",
          ("dept-metro-public-health",)),
    Topic("building_and_planning", Category.CIVIC_SERVICE, "Building and planning",
          "Unauthorised structures, building without a permit, encroachment on roads or public land.",
          ("dept-physical-planning",)),
    Topic("transport", Category.CIVIC_SERVICE, "Transport and traffic",
          "Lorry parks and stations, faulty traffic lights, unauthorised parking, road signs.", ("dept-metro-transport",)),
    Topic("revenue", Category.CIVIC_SERVICE, "Revenue and receipts",
          "Assembly fees, rates, levies and tolls; receipts not given; suspected unofficial collection.",
          ("dept-budget-rating",)),
    Topic("schools", Category.CIVIC_SERVICE, "Schools",
          "Public basic school buildings, furniture, sanitation and supplies.", ("dept-education",)),
    Topic("social_welfare", Category.CIVIC_SERVICE, "Social welfare",
          "Homelessness, street children, support for persons with disability (where no one is in danger).",
          (SOCIAL_WELFARE,)),
    Topic("agriculture", Category.CIVIC_SERVICE, "Animals and urban farming",
          "Stray or roaming livestock, animal rearing in the city, urban farming.", ("dept-food-agriculture",)),
    Topic("other_civic", Category.CIVIC_SERVICE, "Other",
          "Anything else the Assembly is responsible for.", (TRIAGE,)),
    # Public safety: danger to the public at large, not to one identifiable person.
    Topic("fire", Category.PUBLIC_SAFETY, "Fire and fire hazards",
          "A fire, or a clear fire risk: gas leaks, exposed wiring, blocked fire exits.", (GNFS,)),
    Topic("disaster", Category.PUBLIC_SAFETY, "Floods and disasters",
          "Flooding of homes or roads, storm damage, landslides, a disaster in progress.",
          ("dept-disaster-management",)),
    Topic("structural_danger", Category.PUBLIC_SAFETY, "Unsafe structures",
          "A building, wall, billboard or tree at risk of collapse; open manholes; fallen electricity poles.",
          ("dept-works",)),
    Topic("public_crime", Category.PUBLIC_SAFETY, "Crime in public places",
          "Robbery, violence or other crime in a public place, not aimed at the person reporting.", (POLICE,)),
    # Personal safety: chosen by the citizen from these, never by the classifier's
    # judgement of urgency. Always private; always severity 5.
    Topic("abuse", Category.PERSONAL_SAFETY, "Abuse or violence against a person",
          "Someone is hurting you or someone you know.", (POLICE, SOCIAL_WELFARE)),
    Topic("child_at_risk", Category.PERSONAL_SAFETY, "A child at risk",
          "A child is being harmed, neglected or is in danger.", (SOCIAL_WELFARE, POLICE)),
    Topic("sexual_violence", Category.PERSONAL_SAFETY, "Sexual violence",
          "Rape, sexual assault or sexual abuse.", (POLICE, SOCIAL_WELFARE)),
    Topic("threat_to_life", Category.PERSONAL_SAFETY, "A threat to life",
          "Someone has threatened to kill or seriously hurt a person.", (POLICE,)),
    Topic("other_safety", Category.PERSONAL_SAFETY, "Another danger to a person",
          "Someone's safety is at risk in another way.", (POLICE, SOCIAL_WELFARE)),
)

TOPICS_BY_ID = {topic.id: topic for topic in TOPICS}
# Where a personal-safety report goes when nothing more specific is known.
DEFAULT_SAFETY_TOPIC = "other_safety"
TRIAGE_TOPIC = "other_civic"


def topics_in(category: Category) -> list[Topic]:
    return [topic for topic in TOPICS if topic.category == category]


def recipients_for(topic_id: str) -> tuple[str, ...]:
    return TOPICS_BY_ID[topic_id].recipients


def _check_routing() -> None:
    """Fail at import if a topic routes to an unknown team or breaks the safety rules."""
    for topic in TOPICS:
        unknown = [r for r in topic.recipients if r not in RECIPIENT_NAMES]
        if unknown or not topic.recipients:
            raise ValueError(f"topic {topic.id} routes to unknown recipients {unknown or 'none'}")
        if len(topic.recipients) > 1 and not topic.private:
            raise ValueError(f"only personal-safety topics route to two recipients ({topic.id})")


_check_routing()
