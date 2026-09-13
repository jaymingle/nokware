"""Appwrite team IDs: the source of truth for roles in Nokware.

Team membership decides what a user can see and do. Department staff act on
documents for their own department, contributors submit documents for review,
and the MCE team (the MCE and admin accounts) rules on escalated disputes.
"""

DEPARTMENT_NAMES = {
    "dept-central-administration": "Central Administration",
    "dept-finance": "Finance",
    "dept-education": "Education",
    "dept-health": "Health",
    "dept-waste-management": "Waste Management",
    "dept-works": "Works",
    "dept-physical-planning": "Physical Planning",
    "dept-agriculture": "Agriculture",
    "dept-social-welfare": "Social Welfare",
    "dept-disaster-management": "Disaster Management",
    "dept-transport": "Transport",
    "dept-press": "Press",  # assembly-wide documents: press releases, general notices
}
DEPARTMENT_TEAMS = tuple(DEPARTMENT_NAMES)
CONTRIBUTOR_TEAM = "contributor"
MCE_TEAM = "mce"
ALL_TEAMS = (*DEPARTMENT_TEAMS, CONTRIBUTOR_TEAM, MCE_TEAM)
