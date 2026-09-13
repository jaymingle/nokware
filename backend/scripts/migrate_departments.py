"""Move Nokware onto AMA's full department list (ama.gov.gh/departments).

A dry run by default: it prints every change it would make. --yes applies them.
Safe to re-run; each step is skipped once done.

1. Creates each department team that doesn't exist yet. Appwrite team IDs
   can't be renamed, so Health, Transport and Agriculture get new teams
   (dept-metro-public-health, dept-metro-transport, dept-food-agriculture).
2. Adds each old team's members to its new team and gives the seeded account
   its department's new name. The old membership stays until step 5; sign-in
   ignores teams it doesn't know, so the account works throughout.
3. Re-tags Ledger documents by the rules in ama_departments.py. An AMA document
   moving to another department is re-attributed to that department's seeded
   account; while that department has no account yet (seed_users.py), the
   document waits for the next run. Contributor submissions only follow renames.
4. Re-tags case assignments, report recipients and document history rows still
   under an old ID.
5. With --delete-old-teams, deletes each old team once nothing refers to it
   (which also removes its memberships).

Every document change is written, before and after, to
scripts/logs/department_migration_<time>.csv, so it can be reversed.

    backend/.venv/bin/python backend/scripts/migrate_departments.py [--yes] [--delete-old-teams]
"""

import argparse
import csv
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from appwrite.exception import AppwriteException
from appwrite.query import Query

from app.services.appwrite_client import DATABASE_ID, every_record, get_databases, get_teams, get_users
from app.services.appwrite_client import quiet_sdk_deprecation_warnings
from app.services.citizen_reports import ASSIGNMENTS_COLLECTION, REPORTS_COLLECTION
from app.services.ledger_documents import COLLECTION_ID as DOCUMENTS, Origin
from app.teams import DEPARTMENT_NAMES, DEPARTMENT_TEAMS
from ama_departments import RENAMED, ama_department, current_team

HISTORY = "document_history"
LOG_DIR = Path(__file__).resolve().parent / "logs"
DOCUMENT_FIELDS = ["department", "category", "title", "origin", "uploadedBy"]


@dataclass
class Run:
    apply: bool
    changes: int = 0

    def do(self, description: str, action: Any) -> None:
        """Print the change; make it only with --yes."""
        self.changes += 1
        print(f"  {'' if self.apply else '[dry run] '}{description}")
        if self.apply:
            action()


def existing_teams() -> set[str]:
    return {team.id for team in get_teams().list(queries=[Query.limit(100)]).teams}


def members(team: str) -> list[str]:
    return [m.userid for m in get_teams().list_memberships(team, queries=[Query.limit(100)]).memberships]


def create_teams(run: Run, teams: set[str]) -> None:
    print("1. Department teams")
    for team in DEPARTMENT_TEAMS:
        if team not in teams:
            run.do(f"create team {team} ({DEPARTMENT_NAMES[team]})", lambda t=team: get_teams().create(t, t))


def move_members(run: Run, teams: set[str]) -> None:
    print("2. Accounts in renamed departments")
    for old, new in RENAMED.items():
        if old not in teams:
            continue
        already = set(members(new)) if new in teams else set()
        for user_id in members(old):
            if user_id in already:
                continue
            name = DEPARTMENT_NAMES[new]
            run.do(f"add {user_id} to {new} and rename the account \"{name}\"", lambda u=user_id, n=new, m=name: (
                get_teams().create_membership(n, ["member"], user_id=u), get_users().update_name(u, m)))


def seeded_account(team: str, teams: set[str]) -> str | None:
    """The department's one seeded account, if it has been seeded."""
    accounts = members(team) if team in teams else []
    return accounts[0] if len(accounts) == 1 else None


def target_for(document: dict[str, Any]) -> str:
    if document.get("origin") == Origin.AMA_WEBSITE:
        return ama_department(document["department"], document.get("category"), document["title"])
    return current_team(document["department"])  # a contributor's submission only follows a rename


@dataclass(frozen=True)
class DocumentMove:
    document: dict[str, Any]
    target: str
    uploaded_by: str


def plan_documents(teams: set[str]) -> tuple[list[DocumentMove], list[DocumentMove]]:
    """(moves ready to make, moves waiting for the target department's seeded account)."""
    ready, waiting = [], []
    for document in every_record(DOCUMENTS, [Query.select(DOCUMENT_FIELDS)]):
        target = target_for(document)
        if target == document["department"]:
            continue
        keeps_uploader = current_team(document["department"]) == target or document.get("origin") != Origin.AMA_WEBSITE
        account = document["uploadedBy"] if keeps_uploader else seeded_account(target, teams)
        (ready if account else waiting).append(DocumentMove(document, target, account or ""))
    return ready, waiting


def retag_documents(run: Run, teams: set[str], log: list[list[str]]) -> int:
    print("3. Ledger documents")
    ready, waiting = plan_documents(teams)
    for move in ready:
        doc = move.document
        changes = {"department": move.target, "uploadedBy": move.uploaded_by}
        run.do(f"{doc['$id']}: {doc['department']} -> {move.target} | {doc['title'][:70]}",
               lambda i=doc["$id"], c=changes: get_databases().update_document(DATABASE_ID, DOCUMENTS, i, c))
        log.append([doc["$id"], doc["title"], doc["department"], move.target, doc["uploadedBy"], move.uploaded_by])
    for move in waiting:
        print(f"  waiting for {move.target}'s seeded account: {move.document['$id']} | {move.document['title'][:70]}")
    return len(waiting)


def retag_cases(run: Run) -> None:
    print("4. Cases and document history under old IDs")
    db = get_databases()
    for old, new in RENAMED.items():
        for row in every_record(ASSIGNMENTS_COLLECTION, [Query.equal("recipient", old)]):
            run.do(f"assignment {row['$id']}: {old} -> {new}",
                   lambda i=row["$id"], n=new: db.update_document(DATABASE_ID, ASSIGNMENTS_COLLECTION, i, {"recipient": n}))
        for row in every_record(REPORTS_COLLECTION, [Query.contains("recipients", [old])]):
            recipients = [current_team(r) for r in row["recipients"]]
            run.do(f"report {row['$id']}: recipients {row['recipients']} -> {recipients}",
                   lambda i=row["$id"], r=recipients: db.update_document(DATABASE_ID, REPORTS_COLLECTION, i, {"recipients": r}))
        for row in every_record(HISTORY, [Query.equal("department", old)]):
            run.do(f"history {row['$id']}: {old} -> {new}",
                   lambda i=row["$id"], n=new: db.update_document(DATABASE_ID, HISTORY, i, {"department": n}))


def still_referenced(team: str) -> list[str]:
    """What still points at a team: documents, case rows, history, or members not yet in the new team."""
    checks = {DOCUMENTS: Query.equal("department", team), ASSIGNMENTS_COLLECTION: Query.equal("recipient", team),
              REPORTS_COLLECTION: Query.contains("recipients", [team]), HISTORY: Query.equal("department", team)}
    found = [c for c, q in checks.items() if get_databases().list_documents(DATABASE_ID, c, queries=[q, Query.limit(1)]).total]
    unmoved = set(members(team)) - set(members(RENAMED[team]))
    return found + (["members not yet in " + RENAMED[team]] if unmoved else [])


def delete_old_teams(run: Run, teams: set[str]) -> None:
    print("5. Old teams")
    for old in RENAMED:
        if old not in teams:
            continue
        refs = still_referenced(old)
        if refs:
            print(f"  keeping {old}: still referred to by {', '.join(refs)}")
            continue
        run.do(f"delete team {old} (and its memberships)", lambda t=old: get_teams().delete(t))


def write_log(log: list[list[str]]) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    path = LOG_DIR / f"department_migration_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["document_id", "title", "department_before", "department_after", "uploaded_by_before", "uploaded_by_after"])
        writer.writerows(log)
    print(f"\nDocument changes logged to {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="make the changes (default: a dry run)")
    parser.add_argument("--delete-old-teams", action="store_true", help="also delete old teams nothing refers to")
    args = parser.parse_args()
    quiet_sdk_deprecation_warnings()
    run, log = Run(apply=args.yes), []
    try:
        create_teams(run, existing_teams())
        move_members(run, existing_teams())
        waiting = retag_documents(run, existing_teams(), log)
        retag_cases(run)
        if args.delete_old_teams:
            delete_old_teams(run, existing_teams())
    except AppwriteException as exc:
        print(f"\nStopped: Appwrite said {exc.message}. Everything before this point is done; re-run to continue.")
        return 1
    finally:
        if log and args.yes:
            write_log(log)
    mode = "made" if args.yes else "to make (dry run; --yes applies them)"
    print(f"\n{run.changes} change(s) {mode}; {waiting} document(s) waiting for a department's seeded account.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
