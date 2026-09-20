"""Appwrite team IDs: the source of truth for roles in Nokware.

The departments are AMA's own list (ama.gov.gh/departments), under AMA's own names, plus Press for assembly-wide
publications. Environmental Health Services sits under Metro Public Health on AMA's site; it is not a department.

Agencies are outside the Assembly, so they never appear in department lists and have no part in the Ledger.
"""

DEPARTMENT_NAMES = {
    "dept-budget-rating": "Budget & Rating",
    "dept-central-administration": "Central Administration",
    "dept-education": "Department of Education",
    "dept-disaster-management": "Disaster Management & Prevention",
    "dept-finance": "Finance",
    "dept-food-agriculture": "Food & Agriculture",
    "dept-gamada": "GAMADA",
    "dept-human-resource": "Human Resource Department",
    "dept-international-relations": "International Relations",
    "dept-legal": "Legal Department",
    "dept-metro-public-health": "Metro Public Health Department",
    "dept-metro-transport": "Metro Transport",
    "dept-physical-planning": "Physical Planning",
    "dept-social-welfare": "Social Welfare & Community Development",
    "dept-statistics": "Statistics Department",
    "dept-urban-roads": "Urban Roads",
    "dept-waste-management": "Waste Management",
    "dept-works": "Works Department",
    "dept-press": "Press",  # assembly-wide documents: press releases, general notices
}
DEPARTMENT_TEAMS = tuple(DEPARTMENT_NAMES)
AGENCY_NAMES = {
    "agency-police": "Ghana Police Service",
    "agency-gnfs": "Ghana National Fire Service",
}
AGENCY_TEAMS = tuple(AGENCY_NAMES)
RECIPIENT_NAMES = {**DEPARTMENT_NAMES, **AGENCY_NAMES}
SHORT_NAMES = {"dept-social-welfare": "Social Welfare"}
CONTRIBUTOR_TEAM = "contributor"
MCE_TEAM = "mce"
ALL_TEAMS = (*DEPARTMENT_TEAMS, *AGENCY_TEAMS, CONTRIBUTOR_TEAM, MCE_TEAM)


def short_name(team: str) -> str:
    """For someone reporting a danger to a person: "Social Welfare", not the full departmental title."""
    return SHORT_NAMES.get(team) or RECIPIENT_NAMES.get(team, team)
