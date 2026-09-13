"""Filing a citizen report: classification, routing, location and references."""

import pytest

from app.services.report_rules import (
    DEFAULT_SEVERITY,
    ClassificationMethod,
    InvalidReport,
    ModelVerdict,
    classify,
    locate,
    new_reference,
    normalise_reference,
    suggests_danger_to_a_person,
)
from app.services.report_taxonomy import POLICE, SOCIAL_WELFARE, TOPICS, Category

DRAIN = "The big drain on Mudor road is choked and smells."


def test_the_model_picks_the_topic_and_the_routing_table_picks_the_recipient() -> None:
    filed = classify(DRAIN, None, ModelVerdict("civic_service", "drainage", 3))
    assert (filed.category, filed.topic, filed.severity, filed.recipients) == (Category.CIVIC_SERVICE, "drainage", 3, ("dept-works",))
    assert filed.method == ClassificationMethod.AI and not filed.private


def test_severity_is_kept_within_one_to_five() -> None:
    assert classify(DRAIN, None, ModelVerdict("civic_service", "drainage", 9)).severity == 5
    assert classify(DRAIN, None, ModelVerdict("civic_service", "drainage", 0)).severity == 1
    assert classify(DRAIN, None, ModelVerdict("civic_service", "drainage", None)).severity == DEFAULT_SEVERITY


def test_a_citizens_safety_declaration_stands_without_asking_the_model() -> None:
    filed = classify("He comes home drunk and hits me.", "abuse", None)
    assert filed.category == Category.PERSONAL_SAFETY and filed.method == ClassificationMethod.CITIZEN
    assert filed.recipients == (POLICE, SOCIAL_WELFARE)  # two recipients at once
    assert filed.severity == 5


def test_a_declaration_must_be_a_personal_safety_type() -> None:
    with pytest.raises(InvalidReport):
        classify(DRAIN, "drainage", None)


def test_personal_safety_severity_is_always_five_whatever_the_model_says() -> None:
    filed = classify("My neighbour threatened to kill my son.", None, ModelVerdict("personal_safety", "threat_to_life", 2))
    assert (filed.severity, filed.recipients) == (5, (POLICE,))


def test_a_model_that_says_personal_safety_is_believed_even_with_a_muddled_topic() -> None:
    filed = classify("Something is wrong next door.", None, ModelVerdict("personal_safety", "drainage", 3))
    assert filed.category == Category.PERSONAL_SAFETY and filed.topic == "other_safety"


def test_words_of_danger_override_a_civic_verdict() -> None:
    filed = classify("The landlord beats his wife every night.", None, ModelVerdict("civic_service", "other_civic", 2))
    assert filed.private and filed.method == ClassificationMethod.KEYWORD_SCREEN


def test_words_of_danger_do_not_pull_public_crime_out_of_public_safety() -> None:
    filed = classify("Men with a knife assaulted traders at the market.", None, ModelVerdict("public_safety", "public_crime", 4))
    assert filed.category == Category.PUBLIC_SAFETY and filed.recipients == (POLICE,)


def test_when_the_model_fails_danger_goes_private_and_everything_else_to_triage() -> None:
    assert classify("My uncle abuses the children.", None, None).category == Category.PERSONAL_SAFETY
    triaged = classify(DRAIN, None, None)
    assert (triaged.topic, triaged.method, triaged.recipients) == ("other_civic", ClassificationMethod.TRIAGE, ("dept-central-administration",))
    assert classify(DRAIN, None, ModelVerdict("civic_service", "not-a-topic", 3)).method == ClassificationMethod.TRIAGE


@pytest.mark.parametrize("text", ["The traffic beat us to the junction.", "Fix the killer pothole", "Rapeseed oil spill"])
def test_the_danger_screen_ignores_everyday_wording(text: str) -> None:
    assert not suggests_danger_to_a_person(text)


def test_only_personal_safety_topics_route_to_two_recipients() -> None:
    assert all(len(topic.recipients) == 1 for topic in TOPICS if topic.category != Category.PERSONAL_SAFETY)


def test_civic_reports_need_a_ward_and_get_its_sub_metro() -> None:
    assert locate(Category.CIVIC_SERVICE, "mudor", None).sub_metro == "ashiedu-keteke"
    with pytest.raises(InvalidReport):
        locate(Category.CIVIC_SERVICE, None, None)
    with pytest.raises(InvalidReport):
        locate(Category.CIVIC_SERVICE, "atlantis", None)


def test_personal_safety_keeps_no_ward_and_may_keep_no_place_at_all() -> None:
    assert locate(Category.PERSONAL_SAFETY, "kaneshie", None).__dict__ == {"ward": None, "sub_metro": "okaikoi-south"}
    assert locate(Category.PERSONAL_SAFETY, None, None).__dict__ == {"ward": None, "sub_metro": None}


def test_references_are_short_unambiguous_and_forgiving_to_type() -> None:
    reference = new_reference()
    assert len(reference) == 9 and reference[4] == "-"
    assert not set(reference) & set("01OIL")
    assert normalise_reference(reference.lower().replace("-", " ")) == reference
    assert normalise_reference("K7QM-4TX0") is None  # 0 is never used
