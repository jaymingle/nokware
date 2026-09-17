"""Work citizen reports through the staff case routes, against the live services.

Files fresh [TEST] reports through the public API, then acts on them as seeded
accounts (Works, Waste Management, Police, Social Welfare, Finance, the MCE)
with short-lived JWTs minted by the server key; no passwords. In-process, so
background messages finish before each call returns.

This WRITES REAL DATA (reports whose descriptions start "[TEST]");
scripts/delete_test_reports.py lists and removes them.

    backend/.venv/bin/python backend/scripts/case_lifecycle.py
"""

import sys
from typing import Any

from appwrite.query import Query
from report_lifecycle import check, client, failures, file

from app.services import rate_limit
from app.services.appwrite_client import DATABASE_ID, get_databases, get_teams, get_users
from app.services.citizen_reports import NOTIFICATIONS_COLLECTION


def token_for(team: str) -> dict[str, str]:
    user_id = get_teams().list_memberships(team).memberships[0].userid
    return {"Authorization": f"Bearer {get_users().create_jwt(user_id, duration=900).jwt}"}


WORKS, WASTE, POLICE, WELFARE, FINANCE, MCE = (
    token_for(t) for t in ("dept-works", "dept-waste-management", "agency-police", "dept-social-welfare", "dept-finance", "mce")
)
cases: list[str] = []


def new_case(description: str, **fields: Any) -> dict[str, Any]:
    response = file(description, **fields)
    body = response.json()
    cases.append(body["case_id"])
    return body


def act(headers: dict[str, str], case_id: str, action: str, **body: Any) -> Any:
    return client.post(f"/api/cases/{case_id}/{action}", headers=headers, json=body or None)


def queue_ids(headers: dict[str, str]) -> list[str]:
    return [c["case_id"] for c in client.get("/api/cases/queue", headers=headers).json()["cases"]]


def templates(case_id: str) -> list[str]:
    listing = get_databases().list_documents(DATABASE_ID, NOTIFICATIONS_COLLECTION, queries=[Query.equal("caseId", case_id)])
    return sorted(d.data["template"] for d in listing.documents)


def work_escalate_reopen() -> None:
    print("C1 Works resolves; the citizen escalates; the MCE reopens; Works resolves again")
    body = new_case("The drain outside Kinka basic school overflows every time it rains.", ward="kinka", phone="0241234567")
    case_id, ref = body["case_id"], body["reference"]
    check("in Works' queue", case_id in queue_ids(WORKS))
    check("acknowledge -> in progress", act(WORKS, case_id, "acknowledge").json()["status"] == "in_progress")
    check("resolving without a note -> 422", act(WORKS, case_id, "resolve", note="").status_code == 422)
    resolved = act(WORKS, case_id, "resolve", note="[TEST] Drain desilted and cover replaced.")
    check("resolve -> resolved, resolution message sent", resolved.json()["status"] == "resolved" and "resolved" in templates(case_id), resolved.text)
    rate_limit.ESCALATIONS._hits.clear()
    client.post(f"/api/reports/{ref}/escalate", json={"note": "[TEST] It overflowed again on Tuesday."})
    check("Works can't act while escalated -> 409", act(WORKS, case_id, "resolve", note="again").status_code == 409)
    oversight = client.get("/api/cases/oversight", headers=MCE).json()
    row = next(c for c in oversight["cases"] if c["case_id"] == case_id)
    check("the MCE sees it escalated, with reopen and confirm", row["status"] == "escalated"
          and row["allowed_actions"] == ["reassign", "reopen", "confirm-resolution"], row)
    check("reopen -> assigned back to Works", act(MCE, case_id, "reopen", note="[TEST] Clear the whole run to the outfall.").json()["status"] == "assigned")
    act(WORKS, case_id, "resolve", note="[TEST] Whole run cleared to the outfall.")
    check("the final message offers no second escalation", "resolved_after_escalation" in templates(case_id), templates(case_id))
    status = client.get(f"/api/reports/{ref}").json()
    check("the citizen can't escalate twice", status["escalated"] and status["escalate_until"] is None, status)


def reassign() -> None:
    print("C2 the MCE reassigns a misrouted case")
    body = new_case("Nobody has emptied the public bins at Kaneshie lorry station for two weeks.", ward="kaneshie")
    case_id = body["case_id"]
    first = body["recipients"][0]
    source = {"Works Department": "dept-works", "Waste Management": "dept-waste-management"}.get(first, "dept-waste-management")
    target = "dept-works" if source == "dept-waste-management" else "dept-waste-management"
    moved = act(MCE, case_id, "reassign", from_recipient=source, to_recipient=target, reason="[TEST] Moved for the test.")
    check("reassigned, with the reason in the trail", moved.status_code == 200 and any("Moved for the test" in (e["note"] or "") for e in moved.json()["history"]), moved.text)
    check("in the new recipient's queue only", case_id in queue_ids(WORKS if target == "dept-works" else WASTE)
          and case_id not in queue_ids(WASTE if target == "dept-works" else WORKS))
    check("a department can't reassign -> 403", act(WORKS, case_id, "reassign", from_recipient=target, to_recipient=source, reason="x").status_code == 403)


def safety_two_recipients() -> None:
    print("C3 personal safety: Police and Social Welfare, the MCE in outline, Finance sees nothing")
    body = new_case("My husband beats me and took my phone; I use my sister's.", safety_topic="abuse",
                    sub_metro="ablekuma-south", phone="0551234567", notify="true", callback_consent="true")
    case_id = body["case_id"]
    police = client.get(f"/api/cases/{case_id}", headers=POLICE).json()
    check("Police see the report and the number (callback consent)", police["view"] == "full" and police["description"]
          and police["contact"]["phone"] == "+233551234567", police.get("contact"))
    mce = client.get(f"/api/cases/{case_id}", headers=MCE).json()
    check("the MCE sees only the outline", mce["view"] == "oversight" and mce["description"] is None and mce["contact"] is None
          and mce["topic"] == "Personal safety" and mce["place"] is None, mce)
    check("Finance gets not found", client.get(f"/api/cases/{case_id}", headers=FINANCE).status_code == 404)
    check("Police resolve: still open for Social Welfare", act(POLICE, case_id, "resolve", note="[TEST] Statement taken.").json()["status"] == "in_progress")
    done = act(WELFARE, case_id, "resolve", note="[TEST] Counselling arranged.").json()
    check("Social Welfare resolve: resolved", done["status"] == "resolved")
    check("the resolution message is the neutral one", "private_resolved" in templates(case_id), templates(case_id))
    trail = str(client.get(f"/api/cases/{case_id}", headers=MCE).json()["history"])
    check("the MCE's trail has no one's words", "Statement" not in trail and "Counselling" not in trail and "husband" not in trail)


def agency_identity() -> None:
    print("C4 the Police liaison signs in as an agency")
    me = client.get("/api/me", headers=POLICE).json()
    check("role agency, named Ghana Police Service", me["role"] == "agency" and me["agency_name"] == "Ghana Police Service", me)
    check("no part in the Ledger -> 403", client.get("/api/review-queue", headers=POLICE).status_code == 403)


def main() -> int:
    work_escalate_reopen()
    reassign()
    safety_two_recipients()
    agency_identity()
    print(f"\n{len(failures)} failure(s). Cases created:")
    for case_id in cases:
        print(f"  {case_id}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
