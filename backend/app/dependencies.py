"""FastAPI dependencies: sign-in and roles for portal routes, rate limits for public ones.

They are plain (sync) dependencies so the Appwrite round trips run in FastAPI's threadpool.
"""

import hmac
import logging
import math
from collections.abc import Callable
from typing import Annotated

import requests
from appwrite.exception import AppwriteException
from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.services.auth import InvalidTokenError, NoRoleError, Principal, Role, authenticate
from app.services.rate_limit import RateLimit

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


def authorize_job(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    x_job_token: Annotated[str | None, Header()] = None,
) -> str:
    """Returns who called."""
    expected = get_settings().job_token
    if expected and x_job_token and hmac.compare_digest(x_job_token.encode(), expected.encode()):
        return "job-token"
    principal = current_principal(credentials)
    if principal.role != Role.MCE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the MCE can run the deadline job.")
    return principal.user_id


def require_roles(*roles: Role) -> Callable[[Principal], Principal]:
    def dependency(principal: CurrentPrincipal) -> Principal:
        if principal.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role cannot do this.")
        return principal

    return dependency


def rate_limited(limit: RateLimit) -> Callable[[Request], None]:
    def check(request: Request) -> None:
        wait = limit.retry_after(request.client.host if request.client else "unknown")
        if wait is not None:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "Too many requests from this device. Try again in a few minutes.",
                headers={"Retry-After": str(math.ceil(wait))},
            )

    return check
