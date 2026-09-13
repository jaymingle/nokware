"""AMA's full department list, where reports go on it, and which department each AMA document belongs to."""

from ama_departments import RENAMED, ama_department

from app.services.report_taxonomy import recipients_for
from app.teams import DEPARTMENT_NAMES, RECIPIENT_NAMES, short_name


def test_the_list_is_amas_eighteen_departments_plus_press() -> None:
    assert len(DEPARTMENT_NAMES) == 19 and DEPARTMENT_NAMES["dept-press"] == "Press"
    assert DEPARTMENT_NAMES["dept-metro-public-health"] == "Metro Public Health Department"
    assert (DEPARTMENT_NAMES["dept-education"], DEPARTMENT_NAMES["dept-works"]) == ("Department of Education", "Works Department")
    assert not set(RENAMED) & set(DEPARTMENT_NAMES)  # the old IDs are gone


def test_roads_rates_and_public_health_go_to_their_own_departments() -> None:
    assert recipients_for("roads") == ("dept-urban-roads",)
    assert recipients_for("revenue") == ("dept-budget-rating",)
    assert recipients_for("public_health") == ("dept-metro-public-health",)
    assert recipients_for("transport") == ("dept-metro-transport",)
    assert recipients_for("agriculture") == ("dept-food-agriculture",)
    assert recipients_for("street_lighting") == ("dept-works",)


def test_safety_pages_use_the_plain_name_and_staff_the_full_one() -> None:
    assert short_name("dept-social-welfare") == "Social Welfare"
    assert RECIPIENT_NAMES["dept-social-welfare"] == "Social Welfare & Community Development"
    assert short_name("agency-police") == "Ghana Police Service" and short_name("dept-works") == "Works Department"


def test_ama_documents_follow_renames_and_move_where_the_work_is_that_departments_own() -> None:
    assert ama_department("dept-health", "Press Releases", "COVID-19 vaccines") == "dept-metro-public-health"
    assert ama_department("dept-finance", "Budget And Fee Fixing", "2026 AMA Budget") == "dept-budget-rating"
    assert ama_department("dept-press", "International Reports", "GGBS 2020 - Virtual Summit Report") == "dept-international-relations"
    assert ama_department("dept-works", "Policy Documents", "2023 Accra Road Safety Report") == "dept-urban-roads"


def test_documents_about_a_departments_subject_stay_where_they_are() -> None:
    assert ama_department("dept-finance", "Press Releases", "AMA to lock shops over unpaid Property Rates") == "dept-finance"
    assert ama_department("dept-press", "Press Releases", "GAMADA to hold maiden stakeholders' roundtable") == "dept-press"
    assert ama_department("dept-central-administration", "Policy Documents", "AMA Bye-Laws") == "dept-central-administration"
    assert ama_department("dept-works", "Press Releases", "Fight Against Road Traffic Deaths") == "dept-works"
