"""GET /api/me: the signed-in user and the role the portal should show them."""

from fastapi import APIRouter

from app.dependencies import CurrentPrincipal
from app.schemas.me import MeResponse
from app.teams import DEPARTMENT_NAMES

router = APIRouter(prefix="/api", tags=["auth"])


@router.get("/me", response_model=MeResponse)
def me(principal: CurrentPrincipal) -> MeResponse:
    return MeResponse(
        user_id=principal.user_id,
        name=principal.name,
        email=principal.email,
        role=principal.role,
        department=principal.department,
        department_name=DEPARTMENT_NAMES.get(principal.department or ""),
    )
