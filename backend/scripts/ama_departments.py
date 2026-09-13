"""Which department an AMA-imported document belongs to, on AMA's full department list.

AMA's site doesn't say which department published each document. At import
the department came from the Documents Centre folder it was filed under. With
the full list (ama.gov.gh/departments), some documents have a better home, and
three departments have new team IDs. Both the AMA import and
scripts/migrate_departments.py use these rules, so a later
``import_ama_docs.py --refresh-metadata`` agrees with the migration.
"""

# Appwrite team IDs can't be renamed: these departments have new teams.
RENAMED = {
    "dept-health": "dept-metro-public-health",
    "dept-transport": "dept-metro-transport",
    "dept-agriculture": "dept-food-agriculture",
}
BUDGET_RATING = "dept-budget-rating"
INTERNATIONAL_RELATIONS = "dept-international-relations"
URBAN_ROADS = "dept-urban-roads"
WORKS = "dept-works"

# An AMA Documents Centre category that is one department's own work.
CATEGORY_DEPARTMENTS = {
    "Budget And Fee Fixing": BUDGET_RATING,
    "International Reports": INTERNATIONAL_RELATIONS,
}


def current_team(team: str) -> str:
    """A department team ID as it stands now: an old ID gives its new one."""
    return RENAMED.get(team, team)


def ama_department(team: str, category: str | None, title: str) -> str:
    """The department for an AMA document, from where it was filed, its AMA category and its title.

    Road-safety reports filed under Works are Urban Roads' work. Press releases
    *about* a department's subject (rates, GAMADA) stay where they were: they
    aren't that department's publications.
    """
    team = current_team(team)
    if category in CATEGORY_DEPARTMENTS:
        return CATEGORY_DEPARTMENTS[category]
    if team == WORKS and "road safety" in title.lower():
        return URBAN_ROADS
    return team
