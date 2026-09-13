"""FastAPI dependencies for authenticated portal routes.

Use ``CurrentPrincipal`` for any signed-in user, or ``require_roles(...)`` to
restrict a route to particular roles. Both are plain (sync) dependencies, so
the Appwrite round trips run in FastAPI's threadpool.
"""

import logging
from collections.abc import Callable
from typing import Annotated

import requests
from appwrite.exception import AppwriteException
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.auth import InvalidTokenError, NoRoleError, Principal, Role, authenticate

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False, description="Appwrite JWT from account.createJWT()")


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None:
        raise _unauthorized("Sign in to continue.")
    try:
        return authenticate(credentials.credentials)
    except InvalidTokenError:
        raise _unauthorized("Your session has expired. Sign in again.") from None
    except NoRoleError:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "This account has no Nokware role. Ask an administrator to add it to a team."
        ) from None
    except (AppwriteException, requests.RequestException):
        logger.exception("Sign-in check failed")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sign-in is unavailable. Try again shortly.") from None


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def require_roles(*roles: Role) -> Callable[[Principal], Principal]:
    """A dependency that admits only the given roles (403 for anyone else)."""

    def dependency(principal: CurrentPrincipal) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role cannot do this.")
        return principal

    return dependency
