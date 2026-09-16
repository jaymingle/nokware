"""Mint a short-lived Appwrite session token for one seeded account of each portal role.

For local testing of the signed-in portal — an accessibility audit, a browser
pass — without a password going anywhere near the browser or this repository.
The server key creates a token; the browser exchanges it for a session. No
password is read, typed or printed.

    backend/.venv/bin/python backend/scripts/mint_portal_token.py [out.json]

The tokens last 15 minutes and are single use. Write them somewhere temporary
and delete them afterwards; never commit the file.
"""

import json
import sys
from pathlib import Path

from appwrite.query import Query

from app.services.appwrite_client import get_teams, get_users
from app.teams import CONTRIBUTOR_TEAM, DEPARTMENT_TEAMS, MCE_TEAM

MINUTES = 15
ROLES = {"contributor": CONTRIBUTOR_TEAM, "department": DEPARTMENT_TEAMS[0], "mce": MCE_TEAM}


def first_member(team: str) -> str | None:
    found = get_teams().list_memberships(team, queries=[Query.limit(5)])
    return next((str(membership.userid) for membership in found.memberships), None)


def main() -> None:
    out_path = Path(sys.argv[1] if len(sys.argv) > 1 else "portal_tokens.json")
    tokens: dict[str, dict[str, str]] = {}
    for role, team in ROLES.items():
        user_id = first_member(team)
        if not user_id:
            print(f"  no account in team {team}, skipping {role}")
            continue
        token = get_users().create_token(user_id=user_id, length=32, expire=MINUTES * 60)
        tokens[role] = {"team": team, "userId": token.userid, "secret": token.secret}
        print(f"  {role:12} minted for team {team}")
    out_path.write_text(json.dumps(tokens))
    print(f"{len(tokens)} tokens in {out_path}, good for {MINUTES} minutes, single use")


if __name__ == "__main__":
    main()
