"""What a resident can show when they escalate: up to five photos, cleaned as filing cleans them, kept at their stage.

The rules that were already there — fourteen days, once only, and a note — are checked again here with photos in
hand, because the photos are read before the case is written and must not be a way round any of them.
"""

import io
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.routes import case_presenters
from app.routes import reports as routes
from app.services import report_followups
from app.services.report_photos import PhotoRejected
from app.services.workflow import WrongState
from tests.test_case_actions import MCE, WORKS
from tests.test_report_photos import photo_with_gps_and_rotation
from tests.test_report_routes import fresh_limits  # noqa: F401  (the fixture: one escalation must not spend another's)

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
FILED_PHOTO = "reports/c1/01-f11ed0.jpg"
RESOLVED = {
    "$id": "c1", "reference": "K7QM-4TXP", "createdAt": "2026-09-01T10:00:00+00:00", "status": "resolved",
    "resolvedAt": (NOW - timedelta(days=2)).isoformat(), "category": "civic_service", "isSensitive": False,
    "topic": "drainage", "severity": 3, "recipients": ["dept-works"], "wardLocation": "mudor",
    "subMetro": "ashiedu-keteke", "description": "The drain is choked.", "photoIds": [FILED_PHOTO],
}
SAFETY = {**RESOLVED, "$id": "c2", "reference": "M3RD-8WQA", "category": "personal_safety", "isSensitive": True,
          "topic": "abuse", "recipients": ["agency-police", "dept-social-welfare"], "wardLocation": None}
client = TestClient(app)


class Store:
    """The case, the trail and the photo store, in memory. What store_photos was handed is kept whole, so a test
    can look at the bytes that would have gone to MinIO."""

    def __init__(self, case: dict[str, Any]) -> None:
        self.case = dict(case)
        self.stored: list[Any] = []
        self.trail: list[Any] = []

    def update_case(self, case_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        self.case.update(changes)
        return dict(self.case)

    def store_photos(self, case_id: str, photos: list[Any]) -> list[str]:
        self.stored.extend(photos)
        return [f"reports/{case_id}/{position:02d}-esc.jpg" for position, _ in enumerate(photos, start=1)]


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Callable[[dict[str, Any]], Store]:
    def build(case: dict[str, Any]) -> Store:
        s = Store(case)
        monkeypatch.setattr(report_followups, "find", lambda reference: dict(s.case))
        monkeypatch.setattr(report_followups.report_store, "update_case", s.update_case)
        monkeypatch.setattr(report_followups, "store_photos", s.store_photos)
        monkeypatch.setattr(report_followups.case_history, "record", lambda case_id, entry: s.trail.append(entry))
        monkeypatch.setattr(report_followups, "contact_for", lambda case_id: None)
        monkeypatch.setattr(report_followups, "sync_voice_retention", lambda case_id, purge_at: None)
        monkeypatch.setattr(report_followups, "photo_link", lambda name: f"https://photos.test/{name}")
        return s

    return build


def escalate(reference: str = "K7QM-4TXP", photos: list[bytes] | None = None, now: datetime = NOW) -> dict[str, Any]:
    return report_followups.escalate_case(reference, "The water is back at the gate.", now, photos)


def test_an_escalation_photo_is_kept_at_the_stage_it_was_added_at(store: Callable[..., Store]) -> None:
    s = store(RESOLVED)

    case = escalate(photos=[photo_with_gps_and_rotation(), photo_with_gps_and_rotation()])

    assert case["escalationPhotoIds"] == ["reports/c1/01-esc.jpg", "reports/c1/02-esc.jpg"]
    assert case["photoIds"] == [FILED_PHOTO], "what was sent when the report was filed is untouched"
    assert case["status"] == "escalated" and [e.action for e in s.trail] == ["escalated"]


def test_escalating_without_photos_writes_no_photo_attribute_at_all(store: Callable[..., Store]) -> None:
    s = store(RESOLVED)

    assert "escalationPhotoIds" not in escalate()
    assert s.stored == []


def test_nothing_of_the_original_file_is_stored(store: Callable[..., Store]) -> None:
    """The same re-encoding filing does: a fresh JPEG from the pixels, so the GPS position a phone wrote into the
    photo of a house never reaches the Assembly's storage."""
    s = store(RESOLVED)

    escalate(photos=[photo_with_gps_and_rotation()])

    stored = Image.open(io.BytesIO(s.stored[0].data))
    assert stored.format == "JPEG" and len(stored.getexif()) == 0
    assert not {"exif", "xmp", "comment", "icc_profile"} & set(stored.info)


@pytest.mark.parametrize(("photos", "refusal"), [
    ([photo_with_gps_and_rotation()] * 6, "at most 5"),
    ([photo_with_gps_and_rotation(), b"%PDF-1.4 not a photo"], "isn't a JPEG, PNG or WebP"),
])
def test_a_sixth_photo_or_a_file_that_is_not_one_is_refused_and_nothing_is_written(
    store: Callable[..., Store], photos: list[bytes], refusal: str
) -> None:
    s = store(RESOLVED)

    with pytest.raises(PhotoRejected, match=refusal):
        escalate(photos=photos)

    assert s.stored == [] and s.trail == []
    assert s.case["status"] == "resolved" and "escalationPhotoIds" not in s.case


@pytest.mark.parametrize(("case", "refusal"), [
    ({"resolvedAt": (NOW - timedelta(days=15)).isoformat()}, "only within 14 days"),
    ({"escalatedAt": (NOW - timedelta(days=1)).isoformat()}, "already been escalated once"),
])
def test_photos_are_no_way_round_the_window_or_the_once_only_rule(
    store: Callable[..., Store], case: dict[str, Any], refusal: str
) -> None:
    s = store({**RESOLVED, **case})

    with pytest.raises(WrongState, match=refusal):
        escalate(photos=[photo_with_gps_and_rotation()])

    assert s.stored == [] and s.trail == []


def test_the_resident_reads_their_own_photos_on_the_escalation_step(store: Callable[..., Store]) -> None:
    store(RESOLVED)
    case = escalate(photos=[photo_with_gps_and_rotation()])
    trail = [{"action": "escalated", "timestamp": NOW.isoformat(), "staffNote": None},
             {"action": "acknowledged", "timestamp": (NOW - timedelta(days=9)).isoformat(), "staffNote": None}]

    timeline = report_followups.public_status(case, [], NOW, trail)["timeline"]

    escalated = next(step for step in timeline if step["action"] == "escalated")
    assert escalated["photos"] == ["https://photos.test/reports/c1/01-esc.jpg"]
    assert all(step["photos"] == [] for step in timeline if step["action"] != "escalated")


def test_a_personal_safety_status_carries_no_photo_anywhere(
    store: Callable[..., Store], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Whoever holds the reference can open the status page, and on a shared phone that is not always the person
    who filed. The responders have the photos in the portal; the status page shows the stage and nothing else."""
    store(SAFETY)
    monkeypatch.setattr(report_followups.report_locations, "views", lambda case_id: [])
    case = escalate("M3RD-8WQA", [photo_with_gps_and_rotation()])
    assert case["escalationPhotoIds"], "the Police and Social Welfare still get them"

    status = report_followups.public_status(case, [], NOW, report_followups.history_for(case))

    assert all(step["photos"] == [] for step in status["timeline"])
    assert "photos.test" not in str(status) and "reports/c2" not in str(status)


def test_the_portal_tells_an_escalation_photo_from_one_sent_when_the_report_was_filed(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(case_presenters, "photo_link", lambda name: f"https://photos.test/{name}")
    monkeypatch.setattr(case_presenters.case_history, "entries_for", lambda case_id: [])
    monkeypatch.setattr(case_presenters, "contact_for", lambda case_id: None)
    monkeypatch.setattr(case_presenters.report_locations, "shared_at", lambda principal, case, assignments: None)
    escalated = {**RESOLVED, "status": "escalated", "escalatedAt": NOW.isoformat(),
                 "escalationNote": "The water is back at the gate.", "escalationPhotoIds": ["reports/c1/01-esc.jpg"]}
    assignments = [{"caseId": "c1", "recipient": "dept-works", "status": "resolved", "active": True,
                    "assignedAt": NOW.isoformat()}]

    works = case_presenters.detail(WORKS, escalated, assignments)

    assert works.photos == [f"https://photos.test/{FILED_PHOTO}"]
    assert works.escalation_photos == ["https://photos.test/reports/c1/01-esc.jpg"]
    outline = case_presenters.detail(MCE, {**escalated, **SAFETY, "escalationPhotoIds": ["reports/c2/01-esc.jpg"]},
                                     assignments)
    assert (outline.view, outline.photos, outline.escalation_photos) == ("oversight", [], [])


def test_the_escalation_is_multipart_and_carries_the_note_with_the_photos(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: dict[str, Any] = {}

    def escalate_case(reference: str, note: str, now: datetime, photos: list[bytes]) -> dict[str, Any]:
        sent.update(reference=reference, note=note, photos=photos)
        return {**RESOLVED, "status": "escalated", "escalatedAt": now.isoformat()}

    monkeypatch.setattr(routes.report_followups, "escalate_case", escalate_case)
    monkeypatch.setattr(routes.report_followups, "history_for", lambda case: [])
    monkeypatch.setattr(routes.report_followups, "photo_link", lambda name: f"https://photos.test/{name}")
    monkeypatch.setattr(routes.report_store, "assignments_for", lambda case_id: [])
    monkeypatch.setattr(routes, "notify_quietly", lambda case, event: None)
    photo = photo_with_gps_and_rotation()

    response = client.post("/api/reports/K7QM-4TXP/escalate", data={"note": "The water is back at the gate."},
                           files=[("photos", (f"{n}.jpg", photo, "image/jpeg")) for n in range(2)])

    assert response.status_code == 200 and response.json()["escalated"] is True
    assert sent["note"] == "The water is back at the gate." and sent["photos"] == [photo, photo]


def test_the_route_refuses_a_sixth_photo_before_the_case_is_so_much_as_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes.report_followups, "escalate_case",
                        lambda *args: pytest.fail("the case was read for an escalation of six photos"))
    photo = photo_with_gps_and_rotation()

    response = client.post("/api/reports/K7QM-4TXP/escalate", data={"note": "The water is back at the gate."},
                           files=[("photos", (f"{n}.jpg", photo, "image/jpeg")) for n in range(6)])

    assert response.status_code == 422 and "at most 5 photos" in response.json()["detail"]
