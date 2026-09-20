"""The public dashboard: citizen reports and the Ledger in aggregate. No sign-in."""

from fastapi import APIRouter

from app.schemas.dashboard import Dashboard
from app.services import report_dashboard
from app.services.ledger_documents import utc_now

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=Dashboard)
def dashboard() -> Dashboard:
    return Dashboard.model_validate(report_dashboard.dashboard(utc_now()))
