"""Run the portal's document lifecycle end to end against the live services.

Exercises every route through the real API (in-process, so background
ingestion completes before each call returns), acting as seeded accounts with
short-lived JWTs minted by the server key; no passwords are used.

This WRITES REAL DATA: six documents titled "[TEST] ...", their PDFs in MinIO,
their audit entries and, for the four that publish, their chunks. It prints
every created ID at the end so they can be reviewed and deleted.

    backend/.venv/bin/python backend/scripts/portal_lifecycle.py
"""

import sys
import uuid
from datetime import timedelta
from typing import Any

import requests
from fastapi.testclient import TestClient

from app.main import app
from app.services import ledger_documents
from app.services.appwrite_client import get_teams, get_users
from app.services.ledger_documents import utc_now
from app.services.rag import answer_question
from app.teams import DEPARTMENT_TEAMS

RUN = uuid.uuid4().hex[:6].upper()
CATEGORY = "Annual Reports"
SOURCE = "https://ama.gov.gh/documents-centre.php"
client = TestClient(app)
failures: list[str] = []
created: list[str] = []


def check(label: str, ok: bool, detail: Any = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{'' if ok else f'  -> {detail}'}")
    if not ok:
        failures.append(label)


def make_pdf(text: str) -> bytes:
    """A one-page PDF with a real text layer, so ingestion can index it."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    lines = [escaped[i : i + 90] for i in range(0, len(escaped), 90)]
    stream = "BT /F1 11 Tf 72 740 Td 15 TL " + " ".join(f"({line}) '" for line in lines) + " ET"
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream",
    ]
    body, offsets = b"%PDF-1.4\n", []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offsets)
    trailer = f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{len(body)}\n%%EOF\n"
    return body + (xref + trailer).encode("latin-1")


def test_text(scenario: str, version: int = 1) -> str:
    return (
        f"This is a Nokware portal test document, not an official Accra Metropolitan Assembly record. "
        f"Test reference NKW-TEST-{RUN}-{scenario}, version {version}. It exists only to check that uploads, "
        f"reviews, disputes, escalations and automatic publication work. The fictional test footbridge budget "
        f"in this document is GHS 424,242 for scenario {scenario}."
    )


def token_for(team: str) -> dict[str, str]:
    user_id = get_teams().list_memberships(team).memberships[0].userid
    return {"Authorization": f"Bearer {get_users().create_jwt(user_id, duration=900).jwt}"}


FINANCE, WORKS, CONTRIBUTOR, MCE = (token_for(t) for t in ("dept-finance", "dept-works", "contributor", "mce"))


def upload(headers: dict[str, str], scenario: str, **fields: str) -> Any:
    form = {
        "title": f"[TEST] Portal lifecycle {RUN} {scenario}",
        "category": CATEGORY,
        "document_year": "2026",
        **fields,
    }
    files = {"file": ("test.pdf", make_pdf(test_text(scenario)), "application/pdf")}
    response = client.post("/api/documents", headers=headers, data=form, files=files)
    if response.status_code == 201:
        created.append(response.json()["id"])
    return response


def submit(scenario: str) -> str:
    response = upload(CONTRIBUTOR, scenario, department="dept-finance", source_url=SOURCE)
    check(
        f"{scenario}: contributor submits -> held",
        response.status_code == 201 and response.json()["status"] == "held",
        response.text,
    )
    return response.json()["id"]


def act(headers: dict[str, str], document_id: str, action: str, note: str | None = None) -> Any:
    return client.post(f"/api/documents/{document_id}/{action}", headers=headers, json={"note": note} if note else None)


def detail(headers: dict[str, str], document_id: str) -> dict[str, Any]:
    return client.get(f"/api/documents/{document_id}", headers=headers).json()


def agency_upload() -> None:
    print("S1 department upload")
    response = upload(FINANCE, "S1")
    body = response.json()
    check(
        "finance upload -> published under its own name",
        response.status_code == 201 and body["status"] == "published" and body["department"] == "dept-finance",
        response.text,
    )
    check(
        "ingested and searchable", detail(FINANCE, body["id"])["ingestion"] == "searchable", detail(FINANCE, body["id"])
    )


def department_accepts() -> None:
    print("S2 contributor submits, department accepts")
    document_id = submit("S2")
    queue = client.get("/api/review-queue", headers=FINANCE).json()
    item = next((d for d in queue if d["id"] == document_id), None)
    check(
        "in Finance's review queue with accept and dispute",
        item is not None and item["allowed_actions"] == ["accept", "dispute"],
        item,
    )
    check("Works cannot accept it (403)", act(WORKS, document_id, "accept").status_code == 403)
    check("Works cannot see it (403)", client.get(f"/api/documents/{document_id}", headers=WORKS).status_code == 403)
    response = act(FINANCE, document_id, "accept")
    check(
        "Finance accepts -> published",
        response.status_code == 200 and response.json()["status"] == "published",
        response.text,
    )
    check("accepting again is a conflict (409)", act(FINANCE, document_id, "accept").status_code == 409)
    check("ingested and searchable", detail(FINANCE, document_id)["ingestion"] == "searchable")


def escalate_and_overrule() -> None:
    print("S3 dispute, escalate, MCE overrules")
    document_id = submit("S3")
    check("dispute without a reason is refused (422)", act(FINANCE, document_id, "dispute").status_code == 422)
    response = act(FINANCE, document_id, "dispute", "The budget figure does not match our records.")
    body = response.json()
    check(
        "Finance disputes -> disputed, clock stopped",
        body.get("status") == "disputed" and body.get("held_until") is None and body.get("disputed_by_name"),
        response.text,
    )
    check(
        "contributor sees accept-dispute, resubmit, escalate",
        detail(CONTRIBUTOR, document_id)["allowed_actions"] == ["accept-dispute", "resubmit", "escalate"],
    )
    response = act(CONTRIBUTOR, document_id, "escalate", "The figure is from the published AMA budget.")
    body = response.json()
    check(
        "contributor escalates -> still disputed, MCE clock running",
        body.get("status") == "disputed" and body.get("escalated_to_mce") and body.get("held_until"),
        response.text,
    )
    escalations = client.get("/api/escalations", headers=MCE).json()
    check(
        "in the MCE's escalations with uphold and overrule",
        any(d["id"] == document_id and d["allowed_actions"] == ["uphold", "overrule"] for d in escalations),
    )
    check("Finance cannot rule on it (403)", act(FINANCE, document_id, "overrule").status_code == 403)
    response = act(MCE, document_id, "overrule", "The contributor's source is the AMA's own budget.")
    check("MCE overrules -> published", response.json().get("status") == "published", response.text)
    final = detail(MCE, document_id)
    check("ingested and searchable", final["ingestion"] == "searchable", final["ingestion"])
    actions = [entry["action"] for entry in final["history"]]
    check(
        "audit trail: submitted, disputed, escalated, overruled",
        actions == ["submitted", "disputed", "escalated", "overruled"],
        actions,
    )
    # Published and ingested, but a test document: no answer may cite it as the Assembly's, and its figure must not
    # reach a resident from anywhere. Ingestion itself is proved by the search check above.
    answer = answer_question(f"What is the fictional test footbridge budget for test reference NKW-TEST-{RUN}-S3?")
    cited = [s for s in answer["sources"] if s["document_id"] == document_id]
    check(
        "never cited by Ask, though published: it is a test document",
        not cited and "424,242" not in answer["answer"],
        answer["answer"],
    )


def escalate_and_uphold() -> None:
    print("S4 dispute, escalate, MCE upholds")
    document_id = submit("S4")
    act(FINANCE, document_id, "dispute", "Not a Finance document.")
    act(CONTRIBUTOR, document_id, "escalate", "It lists Finance as the author.")
    response = act(MCE, document_id, "uphold", "The department is right.")
    check("MCE upholds -> withdrawn", response.json().get("status") == "withdrawn", response.text)
    check("the contributor can no longer act", detail(CONTRIBUTOR, document_id)["allowed_actions"] == [])


def resubmit_then_withdraw() -> None:
    print("S5 dispute, resubmit, dispute again, contributor withdraws")
    document_id = submit("S5")
    act(FINANCE, document_id, "dispute", "Page 2 is missing.")
    files = {"file": ("v2.pdf", make_pdf(test_text("S5", version=2)), "application/pdf")}
    response = client.post(
        f"/api/documents/{document_id}/resubmit", headers=CONTRIBUTOR, files=files, data={"note": "Added page 2."}
    )
    body = response.json()
    check(
        "resubmit -> held again, count 1, fresh clock, dispute kept",
        body.get("status") == "held"
        and body.get("resubmission_count") == 1
        and body.get("held_until")
        and body.get("dispute_reason") == "Page 2 is missing.",
        response.text,
    )
    act(FINANCE, document_id, "dispute", "Still incomplete.")
    response = client.post(f"/api/documents/{document_id}/resubmit", headers=CONTRIBUTOR, files=files)
    check("a second resubmission is refused (409)", response.status_code == 409, response.text)
    response = act(CONTRIBUTOR, document_id, "accept-dispute")
    check("contributor accepts the dispute -> withdrawn", response.json().get("status") == "withdrawn", response.text)
    files_seen = {entry.get("note") for entry in detail(CONTRIBUTOR, document_id)["history"]}
    check(
        "audit trail keeps both dispute reasons", {"Page 2 is missing.", "Still incomplete."} <= files_seen, files_seen
    )


def clock_runs_out() -> None:
    print("S6 the review clock runs out")
    document_id = submit("S6")
    past = (utc_now() - timedelta(minutes=1)).isoformat()
    ledger_documents.update_document(document_id, {"heldUntil": past})  # simulate 72 hours passing
    check(
        "a dispute after the deadline is refused (409)",
        act(FINANCE, document_id, "dispute", "Too late").status_code == 409,
    )
    check("the job refuses anonymous callers (401)", client.post("/api/jobs/publish-expired").status_code == 401)
    check(
        "the job refuses contributors (403)",
        client.post("/api/jobs/publish-expired", headers=CONTRIBUTOR).status_code == 403,
    )
    response = client.post("/api/jobs/publish-expired", headers=MCE)
    check(
        "the job publishes it",
        response.status_code == 200 and document_id in response.json()["published"],
        response.text,
    )
    final = detail(FINANCE, document_id)
    check(
        "published, searchable, recorded as automatic",
        final["status"] == "published"
        and final["ingestion"] == "searchable"
        and final["history"][-1]["action"] == "auto_published",
        final,
    )


def refusals() -> None:
    print("Refusals")
    check("MCE cannot upload (403)", upload(MCE, "X").status_code == 403)
    check(
        "contributor needs a source URL (422)", upload(CONTRIBUTOR, "X", department="dept-finance").status_code == 422
    )
    check("contributor needs a department (422)", upload(CONTRIBUTOR, "X", source_url=SOURCE).status_code == 422)
    check(
        "department cannot publish for another (403)", upload(FINANCE, "X", department="dept-works").status_code == 403
    )
    files = {"file": ("notes.txt", b"plain text", "text/plain")}
    form = {"title": "[TEST] not a pdf", "category": CATEGORY}
    check(
        "non-PDF is refused (415)",
        client.post("/api/documents", headers=FINANCE, data=form, files=files).status_code == 415,
    )
    check("unknown category is refused (422)", upload(FINANCE, "X", category="Gossip").status_code == 422)
    check("options need sign-in (401)", client.get("/api/departments").status_code == 401)
    departments = client.get("/api/departments", headers=CONTRIBUTOR).json()
    check(
        f"every department on offer ({len(DEPARTMENT_TEAMS)}), including Press",
        len(departments) == len(DEPARTMENT_TEAMS) and {"id": "dept-press", "name": "Press"} in departments,
        len(departments),
    )


def views() -> None:
    """Read-only checks over the documents the scenarios created (S1 first, then S2-S6)."""
    print("Views")
    agency, submitted = created[0], created[1:]
    library = client.get("/api/documents/library", headers=FINANCE, params={"limit": 100}).json()
    check("S1 is in Finance's library", any(d["id"] == agency for d in library["documents"]) and library["total"] >= 1)
    mine = {d["id"] for d in client.get("/api/documents/mine", headers=CONTRIBUTOR).json()}
    check("the contributor's submissions list all five", set(submitted) <= mine)
    check(
        "Works can see a published document", client.get(f"/api/documents/{agency}", headers=WORKS).status_code == 200
    )
    check(
        "Works cannot open a withdrawn one (403)",
        client.get(f"/api/documents/{created[3]}/file", headers=WORKS).status_code == 403,
    )
    link = client.get(f"/api/documents/{agency}/file", headers=WORKS).json()
    check("the file link serves the PDF", requests.get(link["url"], timeout=30).content.startswith(b"%PDF-"))
    check("unknown documents are 404", client.get("/api/documents/no-such-doc", headers=MCE).status_code == 404)


def main() -> int:
    print(f"Run {RUN}")
    for scenario in (
        agency_upload,
        department_accepts,
        escalate_and_overrule,
        escalate_and_uphold,
        resubmit_then_withdraw,
        clock_runs_out,
        refusals,
        views,
    ):
        scenario()
    print(f"\n{len(failures)} failure(s)" + (": " + "; ".join(failures) if failures else ""))
    print("Created [TEST] documents:")
    for document_id in created:
        record = ledger_documents.get_document(document_id)
        print(f"  {document_id}  {record['status']:<10} {record['title']}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
