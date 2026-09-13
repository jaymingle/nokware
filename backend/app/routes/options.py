"""Choices for the portal's upload forms."""

from fastapi import APIRouter

from app.categories import category_names
from app.dependencies import CurrentPrincipal
from app.schemas.documents import Option
from app.teams import DEPARTMENT_NAMES

router = APIRouter(prefix="/api", tags=["options"])


@router.get("/departments", response_model=list[Option])
def departments(_: CurrentPrincipal) -> list[Option]:
    return [Option(id=team, name=name) for team, name in DEPARTMENT_NAMES.items()]


@router.get("/categories", response_model=list[Option])
def categories(_: CurrentPrincipal) -> list[Option]:
    return [Option(id=name, name=name) for name in category_names()]
