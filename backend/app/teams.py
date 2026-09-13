"""Appwrite team IDs: the source of truth for roles in Nokware.

Team membership decides what a user can see and do. Department staff act on
documents for their own department, contributors submit documents for review,
and the MCE team (the MCE and admin accounts) rules on escalated disputes.

Agencies are services outside the Assembly that receive citizen reports about
safety. They are not AMA departments, so they never appear in department lists
and have no part in the Ledger; they see only the cases routed to them.
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
AGENCY_NAMES = {
    "agency-police": "Ghana Police Service",
    "agency-gnfs": "Ghana National Fire Service",
}
AGENCY_TEAMS = tuple(AGENCY_NAMES)
# Everyone a citizen report can be routed to.
RECIPIENT_NAMES = {**DEPARTMENT_NAMES, **AGENCY_NAMES}
CONTRIBUTOR_TEAM = "contributor"
MCE_TEAM = "mce"
ALL_TEAMS = (*DEPARTMENT_TEAMS, *AGENCY_TEAMS, CONTRIBUTOR_TEAM, MCE_TEAM)
