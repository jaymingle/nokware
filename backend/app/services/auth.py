"""Who is calling: verify an Appwrite JWT and resolve the caller's Nokware role.

The browser signs in with Appwrite and sends a short-lived JWT (from
account.createJWT) as a Bearer token. The JWT proves identity only. The role is
always resolved here, from the user's confirmed team memberships read with the
server key, so a client can never claim a role or department it doesn't have.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from appwrite.client import Client
from appwrite.exception import AppwriteException
from appwrite.models import User
from appwrite.services.account import Account

from app.config import get_settings
from app.services.appwrite_client import get_users
from app.teams import ALL_TEAMS, CONTRIBUTOR_TEAM, MCE_TEAM


class Role(StrEnum):
    DEPARTMENT = "department"
    CONTRIBUTOR = "contributor"
    MCE = "mce"


@dataclass(frozen=True)
class Principal:
    user_id: str
    name: str
    email: str
    role: Role
    department: str | None = None  # the department team ID; set only for Role.DEPARTMENT


class InvalidTokenError(Exception):
    """The JWT is expired, revoked, malformed or belongs to a blocked user."""


class NoRoleError(Exception):
    """The user is not in exactly one Nokware role team."""


def resolve_role(team_ids: Iterable[str]) -> tuple[Role, str | None]:
    """Map confirmed team memberships to (role, department team or None).

    Exactly one Nokware team is required: an account in none has no access, and
    an account in several would make "your own department" ambiguous.
    """
    teams = sorted(set(team_ids) & set(ALL_TEAMS))
    if len(teams) != 1:
        raise NoRoleError(f"expected exactly one Nokware team, found {teams or 'none'}")
    team = teams[0]
    if team == MCE_TEAM:
        return Role.MCE, None
    if team == CONTRIBUTOR_TEAM:
        return Role.CONTRIBUTOR, None
    return Role.DEPARTMENT, team


def _user_client(jwt: str) -> Client:
    """A client acting as the JWT's user. Built per request and never cached."""
    settings = get_settings()
    client = Client()
    client.set_endpoint(settings.appwrite_endpoint)
    client.set_project(settings.appwrite_project_id)
    client.set_jwt(jwt)
    return client


def verify_jwt(jwt: str) -> User:
    try:
        return Account(_user_client(jwt)).get()
    except AppwriteException as exc:
        if exc.code == 401:
            raise InvalidTokenError(exc.type or "unauthorized") from exc
        raise


def confirmed_team_ids(user_id: str) -> list[str]:
    memberships = get_users().list_memberships(user_id).memberships
    return [membership.teamid for membership in memberships if membership.confirm]


def authenticate(jwt: str) -> Principal:
    """Verify the JWT with Appwrite, then resolve the role from team membership."""
    user = verify_jwt(jwt)
    role, department = resolve_role(confirmed_team_ids(user.id))
    return Principal(user_id=user.id, name=user.name, email=user.email, role=role, department=department)
