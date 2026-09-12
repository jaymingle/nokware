"""Seed the Nokware Appwrite user accounts and their team memberships.

Accounts come from a TOML config, by default scripts/seed_users.toml, which is
git-ignored. Copy scripts/seed_users.example.toml and set real emails and
passwords.

The whole config is validated before anything is written. Re-running is safe:
an existing user (matched by email) is never recreated and its password is never
changed; only a missing team membership is added. Passwords are never printed.

    backend/.venv/bin/python backend/scripts/seed_users.py [--config PATH] [--dry-run]

Exits 0 on success, 1 on any failure.
"""

import argparse
import sys
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from appwrite.exception import AppwriteException
from appwrite.id import ID
from appwrite.query import Query
from pydantic import ValidationError

from app.config import get_settings, settings_error_summary
from app.services.appwrite_client import get_teams, get_users, quiet_sdk_deprecation_warnings
from app.teams import CONTRIBUTOR_TEAM, DEPARTMENT_TEAMS, MCE_TEAM

DEFAULT_CONFIG = Path(__file__).resolve().parent / "seed_users.toml"
MIN_PASSWORD_LENGTH = 8  # Appwrite's minimum
PLACEHOLDER_PASSWORD = "CHANGE_ME"
MEMBER_ROLES = ["member"]
# One account per department, one contributor, and two MCE-team accounts
# (the MCE and a separate admin account with the same permissions).
EXPECTED_ACCOUNTS = Counter({**dict.fromkeys(DEPARTMENT_TEAMS, 1), CONTRIBUTOR_TEAM: 1, MCE_TEAM: 2})
SCOPE_ERROR = "general_unauthorized_scope"


class ConfigError(Exception):
    """The seed config is missing or invalid; nothing has been written."""


@dataclass(frozen=True)
class SeedUser:
    name: str
    email: str
    password: str
    team: str


def load_config(path: Path) -> list[SeedUser]:
    if not path.exists():
        raise ConfigError(f"{path} not found. Copy seed_users.example.toml to it and set real values.")
    with path.open("rb") as f:
        entries = tomllib.load(f).get("users", [])
    users = []
    for i, entry in enumerate(entries, 1):
        fields = {key: entry.get(key) for key in ("name", "email", "password", "team")}
        blank = [key for key, value in fields.items() if not isinstance(value, str) or not value.strip()]
        if blank:
            raise ConfigError(f"entry {i}: missing or empty {', '.join(blank)}")
        users.append(SeedUser(**{key: value.strip() for key, value in fields.items()}))
    return users


def validate(users: list[SeedUser]) -> None:
    emails = Counter(user.email.lower() for user in users)
    duplicates = [email for email, count in emails.items() if count > 1]
    if duplicates:
        raise ConfigError(f"duplicate email(s): {', '.join(duplicates)}")
    for user in users:
        if user.password == PLACEHOLDER_PASSWORD or len(user.password) < MIN_PASSWORD_LENGTH:
            raise ConfigError(f"{user.email}: set a real password of at least {MIN_PASSWORD_LENGTH} characters")
    teams = Counter(user.team for user in users)
    if teams != EXPECTED_ACCOUNTS:
        wrong = sorted(t for t in teams | EXPECTED_ACCOUNTS if teams[t] != EXPECTED_ACCOUNTS[t])
        detail = ", ".join(f"{t} has {teams[t]}, needs {EXPECTED_ACCOUNTS[t]}" for t in wrong)
        raise ConfigError(f"expected {EXPECTED_ACCOUNTS.total()} accounts: {detail}")


def check_teams_exist() -> None:
    for team in EXPECTED_ACCOUNTS:
        try:
            get_teams().get(team)
        except AppwriteException as exc:
            if exc.code == 404:
                raise ConfigError(f"team '{team}' does not exist in Appwrite") from exc
            raise


def find_user_id(email: str) -> str | None:
    users = get_users().list(queries=[Query.equal("email", email)]).users
    return users[0].id if users else None


def is_member(team: str, user_id: str) -> bool:
    memberships = get_teams().list_memberships(team, queries=[Query.equal("userId", user_id)])
    return memberships.total > 0


def other_teams(user_id: str, team: str) -> list[str]:
    memberships = get_users().list_memberships(user_id).memberships
    return [m.teamid for m in memberships if m.teamid != team]


def seed_user(user: SeedUser, dry_run: bool) -> tuple[bool, bool, str]:
    """Ensure one user and their membership. Returns (created, joined, message)."""
    user_id = find_user_id(user.email)
    created = user_id is None
    if created and dry_run:
        return True, True, "would create user · would add to team"
    if created:
        user_id = get_users().create(ID.unique(), email=user.email, password=user.password, name=user.name).id
    joined = not is_member(user.team, user_id)
    if joined and not dry_run:
        get_teams().create_membership(user.team, MEMBER_ROLES, user_id=user_id)
    verb = "would add to team" if dry_run else "added to team"
    message = f"{'created' if created else 'exists'} · {verb if joined else 'already a member'}"
    extra = other_teams(user_id, user.team)
    if extra:
        message += f" · WARNING: also in {', '.join(extra)}"
    return created, joined, message


def seed_all(users: list[SeedUser], dry_run: bool) -> int:
    created = joined = failed = 0
    for user in users:
        label = f"  {user.email:40} {user.team:28}"
        try:
            was_created, was_joined, message = seed_user(user, dry_run)
        except AppwriteException as exc:
            if exc.type == SCOPE_ERROR:
                print(f"{label} STOPPED: the API key lacks a required scope. {exc.message}")
                return 1
            failed += 1
            print(f"{label} FAILED: {exc.message}")
            continue
        created += was_created
        joined += was_joined
        print(f"{label} {message}")
    action = "would be" if dry_run else "were"
    print(f"\n{created} user(s) {action} created, {joined} membership(s) {action} added, {failed} failed.")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Nokware Appwrite users and team memberships.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="path to the seed TOML config")
    parser.add_argument("--dry-run", action="store_true", help="show what would change without writing")
    args = parser.parse_args()
    quiet_sdk_deprecation_warnings()
    try:
        get_settings()
        users = load_config(args.config)
        validate(users)
        check_teams_exist()
    except ValidationError as exc:
        print(settings_error_summary(exc))
        return 1
    except (ConfigError, tomllib.TOMLDecodeError) as exc:
        print(f"Config error (nothing written): {exc}")
        return 1
    except AppwriteException as exc:
        print(f"Appwrite error before seeding (nothing written): {exc.message}")
        return 1
    print(f"Seeding {len(users)} Nokware accounts{' (dry run, nothing written)' if args.dry_run else ''}\n")
    return seed_all(users, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
