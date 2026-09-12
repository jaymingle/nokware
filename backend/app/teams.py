"""Appwrite team IDs: the source of truth for roles in Nokware.

Team membership decides what a user can see and do. Department staff act on
documents for their own department, contributors submit documents for review,
and the MCE team (the MCE and admin accounts) rules on escalated disputes.
"""

DEPARTMENT_TEAMS = (
    "dept-central-administration",
    "dept-finance",
    "dept-education",
    "dept-health",
    "dept-waste-management",
    "dept-works",
    "dept-physical-planning",
    "dept-agriculture",
    "dept-social-welfare",
    "dept-disaster-management",
    "dept-transport",
    "dept-press",  # assembly-wide documents: press releases, general notices
)
CONTRIBUTOR_TEAM = "contributor"
MCE_TEAM = "mce"
ALL_TEAMS = (*DEPARTMENT_TEAMS, CONTRIBUTOR_TEAM, MCE_TEAM)
