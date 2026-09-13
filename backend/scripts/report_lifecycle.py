"""Run citizen reports end to end against the live services (Appwrite, MinIO, Gemini).

Files reports through the real API, in-process (so background messages finish
before each call returns), then reads back what was stored: the case, its
assignments, contact, outbox and audit trail, and the photo in MinIO.

This WRITES REAL DATA: reports whose descriptions start "[TEST]", with their
assignments, contacts, outbox rows, audit entries and one photo each where
attached. It prints every case ID at the end;
scripts/delete_test_reports.py lists and (with --yes) removes them.

Resolution is a portal action (R3); until then this script resolves a case by
writing the same fields the portal will, to test escalation.

    backend/.venv/bin/python backend/scripts/report_lifecycle.py
"""

import io
import sys
from datetime import timedelta
from typing import Any

from appwrite.query import Query
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.services import case_history, rate_limit, report_store
from app.services.appwrite_client import DATABASE_ID, get_databases
from app.services.citizen_reports import NOTIFICATIONS_COLLECTION
from app.services.ledger_documents import utc_now
from app.services.report_contacts import contact_for
from app.services.report_followups import sync_contact_retention
from app.services.storage import get_minio

client = TestClient(app)
failures: list[str] = []
created: list[str] = []
GPS_IFD = 0x8825


def check(label: str, ok: bool, detail: Any = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{'' if ok else f'  -> {detail}'}")
    if not ok:
        failures.append(label)


def gps_photo() -> bytes:
    image = Image.new("RGB", (80, 40), "green")
    exif = image.getexif()
    exif[0x0112] = 6
    exif.get_ifd(GPS_IFD).update({1: "N", 2: (5.0, 33.0, 0.0), 3: "W", 4: (0.0, 12.0, 0.0)})
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif.tobytes())
    return out.getvalue()


def file(description: str, photos: list[bytes] | None = None, **fields: Any) -> Any:
    rate_limit.SUBMISSIONS._hits.clear()  # the script files more than a citizen would
    files = [("photos", (f"p{i}.jpg", data, "image/jpeg")) for i, data in enumerate(photos or [])]
    response = client.post("/api/reports", data={"description": f"[TEST] {description}", **fields}, files=files or None)
    if response.status_code == 201:
        created.append(response.json()["case_id"])
    return response


def outbox(case_id: str) -> list[dict[str, Any]]:
    listing = get_databases().list_documents(DATABASE_ID, NOTIFICATIONS_COLLECTION, queries=[Query.equal("caseId", case_id)])
    return [d.data for d in listing.documents]


def civic_report() -> str:
    print("R1 civic report, with a GPS-tagged photo and a phone number")
    response = file("The main drain on Mudor road is choked with plastic and water stands at the school gate.",
                    [gps_photo()], ward="mudor", phone="024 123 4567")
    body = response.json()
    check("filed -> 201, routed to Works", response.status_code == 201 and body["recipients"] == ["Works Department"], response.text)
    check("topic shown, not private, messages on", body["topic"] == "Drainage and flooding" and not body["private"] and body["messages_on"], body)
    case = report_store.find_case(body["case_id"])
    check("stored with ward and sub-metro, severity 1-5", case["wardLocation"] == "mudor" and case["subMetro"] == "ashiedu-keteke"
          and 1 <= case["severity"] <= 5, case)
    check("no number anywhere on the case", "4123" not in str(case), "number leaked")
    photo = get_minio().get_object("nokware-report-photos", case["photoIds"][0]).read()
    stored = Image.open(io.BytesIO(photo))
    check("photo stored upright with no EXIF or GPS", stored.size == (40, 80) and len(stored.getexif()) == 0, stored.info)
    check("one active assignment to Works", [a["recipient"] for a in report_store.assignments_for(case["$id"])] == ["dept-works"])
    rows = outbox(case["$id"])
    check("received SMS in the outbox, recorded not sent, no number", len(rows) == 1 and rows[0]["status"] == "not_sent"
          and rows[0]["channel"] == "sms" and "+233" not in rows[0]["body"], rows)
    actions = [e["action"] for e in case_history.entries_for(case["$id"])]
    check("trail: submitted, classified, assigned, notified", actions == ["submitted", "classified", "assigned", "notified"], actions)
    return case["$id"]


def lookups(case_id: str) -> None:
    print("R2 following a case by reference")
    case = report_store.find_case(case_id)
    typed = case["reference"].lower().replace("-", " ")
    by_ref = client.get(f"/api/reports/{typed}").json()
    check("found by the reference as typed (lower case, space)", by_ref.get("reference") == case["reference"], by_ref)
    check("found by case ID too", client.get(f"/api/reports/{case_id}").json().get("reference") == case["reference"])
    check("shows topic, ward, department", (by_ref["topic"], by_ref["ward"], by_ref["recipients"]) == ("Drainage and flooding", "Mudor", ["Works Department"]), by_ref)
    check("unknown reference -> 404", client.get("/api/reports/ZZZZ-2222").status_code == 404)


def declared_safety() -> None:
    print("R3 personal safety, declared by the citizen")
    response = file("My uncle beats my mother every night and says he will hurt her if she leaves.", safety_topic="abuse",
                    ward="kaneshie", phone="0241234567", notify="false", callback_consent="true")
    body = response.json()
    check("filed, private, to Police and Social Welfare", response.status_code == 201 and body["private"]
          and body["recipients"] == ["Ghana Police Service", "Social Welfare"] and body["topic"] is None, response.text)
    case = report_store.find_case(body["case_id"])
    check("severity 5, citizen-declared, no ward, sub-metro kept", case["severity"] == 5 and case["classifiedBy"] == "citizen"
          and case["wardLocation"] is None and case["subMetro"] == "okaikoi-south", case)
    check("two assignments", len(report_store.assignments_for(case["$id"])) == 2)
    check("no message: not opted in", outbox(case["$id"]) == [] and not body["messages_on"])
    contact = contact_for(case["$id"])
    check("callback consent stored, messages off", contact["callbackConsent"] is True and contact["notify"] is False, contact)
    trail = str(case_history.entries_for(case["$id"]))
    check("the trail never quotes the report", "beats" not in trail and "uncle" not in trail)
    status = client.get(f"/api/reports/{case['reference']}").json()
    check("status shows only the stage", status["private"] and status["stage"] == "received" and status["recipients"] == []
          and status["topic"] is None, status)


def classifier_finds_danger() -> None:
    print("R4 the classifier files it as personal safety: messages held, asked again")
    response = file("The children in the house behind the market are beaten and locked in every day.",
                    ward="kaneshie", phone="0241234567")
    body = response.json()
    check("private, held for consent, token issued", response.status_code == 201 and body["private"]
          and body["held_for_consent"] and not body["messages_on"] and body["preferences_token"], response.text)
    ref, token = body["reference"], body["preferences_token"]
    wrong = client.post(f"/api/reports/{ref}/preferences", json={"notify": True, "callback_consent": False},
                        headers={"X-Receipt-Token": "guess"})
    check("a wrong token -> 403", wrong.status_code == 403, wrong.text)
    right = client.post(f"/api/reports/{ref}/preferences", json={"notify": True, "callback_consent": True},
                        headers={"X-Receipt-Token": token})
    check("the right token -> messages on", right.status_code == 200 and right.json()["messages_on"], right.text)
    rows = outbox(body["case_id"])
    check("the neutral received message follows", len(rows) == 1 and rows[0]["template"] == "private_submitted"
          and "report" not in rows[0]["body"].lower(), rows)
    again = client.post(f"/api/reports/{ref}/preferences", json={"notify": False, "callback_consent": False},
                        headers={"X-Receipt-Token": token})
    check("the token works once only", again.status_code == 403, again.text)


def public_safety_whatsapp() -> None:
    print("R5 public safety, WhatsApp only")
    response = file("Exposed electrical wires hang over the stalls at Kaneshie market and spark when it rains.",
                    ward="kaneshie", whatsapp="+44 7700 900123")
    body = response.json()
    case_id = body.get("case_id", "")
    check("to GNFS", response.status_code == 201 and body["recipients"] == ["Ghana National Fire Service"], response.text)
    rows = outbox(case_id)
    check("one WhatsApp message", [r["channel"] for r in rows] == ["whatsapp"], rows)


def refusals() -> None:
    print("R6 refusals: nothing stored")
    check("landline number -> 422", file("The streetlight at Avenor junction is out.", ward="avenor", phone="0302123456").status_code == 422)
    check("unknown ward -> 422", file("The streetlight at Avenor junction is out.", ward="atlantis").status_code == 422)
    check("eleven photos -> 422", file("Refuse everywhere on our street.", [gps_photo()] * 11, ward="bubui").status_code == 422)
    check("a PDF as a photo -> 422", file("Refuse everywhere.", [b"%PDF-1.4 nope"], ward="bubui").status_code == 422)


def escalation(case_id: str) -> None:
    print("R7 escalation (resolution simulated until the portal's R3)")
    rate_limit.ESCALATIONS._hits.clear()  # R4's preferences calls share this limit
    now = utc_now()
    for a in report_store.assignments_for(case_id):
        report_store.update_assignment(a["$id"], {"status": "resolved", "resolvedAt": now.isoformat(), "resolutionNote": "[TEST] Drain desilted."})
    resolved = report_store.update_case(case_id, {"status": "resolved", "resolvedAt": now.isoformat()})
    sync_contact_retention(resolved)
    purge = contact_for(case_id)["purgeAt"]
    check("numbers set to be deleted 14 + 30 days after resolution", purge and purge.startswith((now + timedelta(days=44)).date().isoformat()), purge)
    ref = resolved["reference"]
    check("escalating without a reason -> 422", client.post(f"/api/reports/{ref}/escalate", json={"note": ""}).status_code == 422)
    response = client.post(f"/api/reports/{ref}/escalate", json={"note": "[TEST] Water still stands at the gate."})
    check("escalated", response.status_code == 200 and response.json()["escalated"], response.text)
    check("numbers kept while it is open again", contact_for(case_id)["purgeAt"] is None)
    check("escalation acknowledged by SMS", [r["event"] for r in outbox(case_id)] == ["submitted", "escalated"])
    check("a second escalation -> 409", client.post(f"/api/reports/{ref}/escalate", json={"note": "again"}).status_code == 409)


def main() -> int:
    case_id = civic_report()
    lookups(case_id)
    declared_safety()
    classifier_finds_danger()
    public_safety_whatsapp()
    refusals()
    escalation(case_id)
    print(f"\n{len(failures)} failure(s). Cases created:")
    for created_id in created:
        print(f"  {created_id}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
