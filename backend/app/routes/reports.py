"""Citizen reports: public routes, no sign-in. Rate-limited per client address."""

from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Header, UploadFile

from app import contacts, safety_steps
from app.dependencies import rate_limited
from app.schemas.documents import Option
from app.schemas.reports import (
    EscalationRequest,
    PreferencesRequest,
    PreferencesResult,
    ReportOptions,
    ReportReceipt,
    ReportStatus,
    SafetyType,
    SubMetroOption,
)
from app.services import rate_limit, report_followups, report_intake, report_store
from app.services.citizen_reports import DESCRIPTION_MAX, MAX_PHOTOS, NotificationEvent
from app.services.ledger_documents import utc_now
from app.services.notifications import notify_quietly
from app.services.report_intake import DESCRIPTION_MIN, ReportSubmission
from app.services.report_photos import MAX_PHOTO_BYTES, PhotoRejected
from app.services.report_taxonomy import TOPICS_BY_ID, Category, topics_in
from app.teams import RECIPIENT_NAMES, short_name
from app.wards import sub_metros, wards

router = APIRouter(prefix="/api/reports", tags=["reports"])

Submissions = Depends(rate_limited(rate_limit.SUBMISSIONS))
Lookups = Depends(rate_limited(rate_limit.LOOKUPS))
Escalations = Depends(rate_limited(rate_limit.ESCALATIONS))


@router.get("/options", response_model=ReportOptions)
def options() -> ReportOptions:
    grouped = [
        SubMetroOption(
            id=sm.id, name=sm.name, wards=[Option(id=w.id, name=w.name) for w in wards().values() if w.sub_metro == sm.id]
        )
        for sm in sub_metros().values()
    ]
    safety = [
        SafetyType(id=t.id, label=t.label, guide=t.guide, recipients=[short_name(r) for r in t.recipients])
        for t in topics_in(Category.PERSONAL_SAFETY)
    ]
    return ReportOptions(
        sub_metros=grouped,
        safety_types=safety,
        max_photos=MAX_PHOTOS,
        max_photo_bytes=MAX_PHOTO_BYTES,
        description_min=DESCRIPTION_MIN,
        description_max=DESCRIPTION_MAX,
        safety_contacts=contacts.safety_contacts(None),
        safety_steps=list(safety_steps.STEPS),
    )


def _blank_to_none(value: str | None) -> str | None:
    return (value.strip() or None) if value else None


def report_form(
    description: Annotated[str, Form()],
    ward: Annotated[str | None, Form()] = None,
    sub_metro: Annotated[str | None, Form()] = None,
    safety_topic: Annotated[str | None, Form(description="Set only by the personal-safety form.")] = None,
    phone: Annotated[str | None, Form()] = None,
    whatsapp: Annotated[str | None, Form()] = None,
    notify: Annotated[bool, Form(description="Safety form: the citizen's opt-in to messages.")] = False,
    callback_consent: Annotated[bool, Form(description="Safety form: Police and Social Welfare may call.")] = False,
) -> ReportSubmission:
    return ReportSubmission(
        description=description,
        ward=_blank_to_none(ward),
        sub_metro=_blank_to_none(sub_metro),
        safety_topic=_blank_to_none(safety_topic),
        phone=_blank_to_none(phone),
        whatsapp=_blank_to_none(whatsapp),
        notify=notify,
        callback_consent=callback_consent,
    )


def _read_photos(photos: list[UploadFile]) -> list[bytes]:
    if len(photos) > MAX_PHOTOS:
        raise PhotoRejected(f"Attach at most {MAX_PHOTOS} photos.")
    return [photo.file.read(MAX_PHOTO_BYTES + 1) for photo in photos if photo.filename]


def _receipt(receipt: report_intake.Receipt) -> ReportReceipt:
    case = receipt.case
    return ReportReceipt(
        reference=case["reference"],
        case_id=case["$id"],
        private=case["isSensitive"],
        topic=None if case["isSensitive"] else TOPICS_BY_ID[case["topic"]].label,
        # Someone reporting a danger to a person reads plain names ("Social Welfare").
        recipients=[short_name(r) if case["isSensitive"] else RECIPIENT_NAMES[r] for r in case["recipients"]],
        messages_on=receipt.messages_on,
        held_for_consent=receipt.held_for_consent,
        preferences_token=receipt.preferences_token,
        contacts=contacts.for_report(case["topic"], case.get("subMetro")),
    )


@router.post("", response_model=ReportReceipt, status_code=201, dependencies=[Submissions])
def file_report(
    tasks: BackgroundTasks,
    submission: Annotated[ReportSubmission, Depends(report_form)],
    photos: Annotated[list[UploadFile], File(description="Up to 10 JPEG, PNG or WebP photos.")] = [],  # noqa: B006
) -> ReportReceipt:
    receipt = report_intake.submit(submission, _read_photos(photos), utc_now())
    if receipt.messages_on:
        tasks.add_task(notify_quietly, receipt.case, NotificationEvent.SUBMITTED)
    return _receipt(receipt)


def _status(case: dict[str, Any]) -> ReportStatus:
    assignments = report_store.assignments_for(case["$id"])
    view = ReportStatus.model_validate(report_followups.public_status(case, assignments, utc_now()))
    if not view.private:  # anyone with the reference sees this; a safety case shows no hint of what it is
        view.contacts = contacts.for_report(case["topic"], case.get("subMetro"))
    return view


@router.get("/{reference}", response_model=ReportStatus, dependencies=[Lookups])
def status(reference: str) -> ReportStatus:
    return _status(report_followups.find(reference))


@router.post("/{reference}/escalate", response_model=ReportStatus, dependencies=[Escalations])
def escalate(reference: str, request: EscalationRequest, tasks: BackgroundTasks) -> ReportStatus:
    case = report_followups.escalate_case(reference, request.note, utc_now())
    tasks.add_task(notify_quietly, case, NotificationEvent.ESCALATED)
    return _status(case)


@router.post("/{reference}/preferences", response_model=PreferencesResult, dependencies=[Escalations])
def preferences(
    reference: str,
    request: PreferencesRequest,
    tasks: BackgroundTasks,
    receipt_token: Annotated[str, Header(alias="X-Receipt-Token")],
) -> PreferencesResult:
    choice = report_followups.Preferences(notify=request.notify, callback_consent=request.callback_consent)
    case, messages_on = report_followups.set_preferences(reference, receipt_token, choice, utc_now())
    if messages_on:  # the "received" message they would otherwise have had
        tasks.add_task(notify_quietly, case, NotificationEvent.SUBMITTED)
    return PreferencesResult(messages_on=messages_on)
