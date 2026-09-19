"""Petitions: public pages, the creator's own petitions (by a confirmed phone), what residents say under one, the
contributors' queue of what has been reported, and the MCE's responses.

Nobody approves a petition here. A draft that passes the screen is published by the person who wrote it; what comes
down, comes down on a named ground, by a contributor who neither started it nor signed it.
"""

from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Header, Query, Request, UploadFile

from app.config import get_settings
from app.dependencies import client_address, rate_limited, refuse_if_over, require_roles
from app.routes import petition_presenters as present
from app.schemas.documents import Option
from app.schemas.petitions import (
    AreaOption,
    AwaitingResponse,
    Comment,
    CommentPage,
    CommentRemovalRequest,
    CommentReportRequest,
    CommentRequest,
    DismissRequest,
    DraftRequest,
    EditRequest,
    LedgerMatch,
    LedgerSearchRequest,
    MyPetitions,
    MySignature,
    NamedSignatures,
    OwnPetition,
    PetitionDetail,
    PetitionOptions,
    PetitionPage,
    RemovalRequest,
    ReportedComment,
    ReportFiled,
    ReportQueue,
    ReportRequest,
    ResponseRequest,
    ScreenRequest,
    ScreenResult,
    SignRequest,
    SignResult,
    SubmitRequest,
    Tombstone,
    Verification,
)
from app.services import (
    petition_comments,
    petition_images,
    petition_ledger,
    petition_removals,
    petition_reports,
    petition_responses,
    petition_screen,
    petition_signatures,
    petition_updates,
    petitions,
    phone_proof,
    rate_limit,
)
from app.services.auth import Principal, Role
from app.services.ledger_documents import utc_now
from app.services.petition_grounds import Dismissal, Ground, in_plain_words
from app.services.petition_rules import (
    DOCUMENTS_MAX,
    IMAGES_MAX,
    OPEN_FOR,
    REMOVAL_NOTE_MAX,
    REPORT_NOTE_MAX,
    RESPONSE_WINDOW,
    Draft,
    InvalidPetition,
    Response,
    Scope,
    petition_topics,
    version_of,
)
from app.services.petition_updates import Update
from app.services.report_photos import MAX_PHOTO_BYTES
from app.services.report_taxonomy import TOPICS_BY_ID
from app.wards import sub_metros, wards

router = APIRouter(prefix="/api/petitions", tags=["petitions"])
Checks = Depends(rate_limited(rate_limit.PETITION_CHECKS))
Changes = Depends(rate_limited(rate_limit.PETITION_CHANGES))
Signing = Depends(rate_limited(rate_limit.SIGNING))
Mce = Annotated[Principal, Depends(require_roles(Role.MCE))]
Contributor = Annotated[Principal, Depends(require_roles(Role.CONTRIBUTOR))]
PAGE_MAX = 50
GROUPS = petitions.PUBLIC_GROUPS


def confirmed_phone(x_phone_proof: Annotated[str | None, Header()] = None) -> phone_proof.Proof:
    """401 if the proof is missing, altered or expired."""
    return phone_proof.open_proof(x_phone_proof, utc_now())


Phone = Annotated[phone_proof.Proof, Depends(confirmed_phone)]


def _draft(request: DraftRequest, images: tuple[str, ...]) -> Draft:
    return Draft(request.title, request.body, request.topic, Scope(request.scope), request.ward, request.issue,
                 tuple(request.documents), images)


def _stored_images(images: list[UploadFile], keep: tuple[str, ...] = ()) -> tuple[str, ...]:
    """What the petition will show: the images kept from the version before, then whatever was just uploaded."""
    sent = [image.file.read(MAX_PHOTO_BYTES + 1) for image in images if image.filename]
    return (*keep, *petition_images.store_images(sent, IMAGES_MAX - len(keep)))


@router.get("/options", response_model=PetitionOptions)
def options() -> PetitionOptions:
    settings = get_settings()
    return PetitionOptions(
        topics=[Option(id=t.id, name=t.label) for t in petition_topics()],
        areas=[AreaOption(id=w.id, name=w.name, sub_metro=sub_metros()[w.sub_metro].name) for w in wards().values()],
        threshold_area=settings.petition_threshold_area, threshold_metro=settings.petition_threshold_metro,
        open_days=OPEN_FOR.days, response_days=RESPONSE_WINDOW.days, max_images=IMAGES_MAX,
        max_documents=DOCUMENTS_MAX, report_note_max=REPORT_NOTE_MAX, removal_note_max=REMOVAL_NOTE_MAX,
        grounds=present.grounds(), dismissal_reasons=present.dismissal_reasons(),
        status_words=present.status_catalogue(),
        verification=Verification(whatsapp=phone_proof.whatsapp_available(), ussd_code=phone_proof.ussd_code(),
                                  sms=phone_proof.sms_available()),
    )


@router.get("", response_model=PetitionPage)
def published(
    group: Literal["open", "awaiting", "responded", "closed"] = "open",
    topic: str | None = None,
    limit: Annotated[int, Query(ge=1, le=PAGE_MAX)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PetitionPage:
    found, total = petitions.list_public(GROUPS[group], topic, limit, offset)
    return PetitionPage(petitions=[present.card(p) for p in found], total=total, counts=petitions.public_counts(),
                        removals=present.removals(petition_removals.removals_by_ground()),
                        topics=[Option(id=t.id, name=t.label) for t in petition_topics()])


@router.get("/responses", response_model=list[AwaitingResponse])
def responses(_: Mce) -> list[AwaitingResponse]:
    return [present.awaiting(p) for p in petitions.awaiting_response()]


@router.get("/reports", response_model=ReportQueue)
def reported(_: Contributor) -> ReportQueue:
    """What readers have reported, newest first: the petitions, and the comments standing under them."""
    return ReportQueue(reports=[present.reported(item) for item in petition_reports.queue()],
                       comments=[_reported_comment(item) for item in petition_comments.queue()],
                       grounds=present.grounds(), dismissal_reasons=present.dismissal_reasons())


def _comment(seen: petition_comments.Seen) -> Comment:
    return Comment(id=seen.id, name=seen.name, text=seen.text, at=seen.at, removed=seen.removed)


def _reported_comment(item: petition_comments.ReportedComment) -> ReportedComment:
    ground = Ground(item.report["ground"])
    return ReportedComment(id=item.report["$id"], reported_at=item.report["createdAt"], ground=ground.value,
                           ground_words=in_plain_words(ground), note=item.report.get("note"),
                           reports_on_this_comment=item.reports_on_this_comment, code=item.report["code"],
                           comment=_comment(item.comment))


@router.post("/reports/{report_id}/dismiss", response_model=ReportQueue, dependencies=[Changes])
def dismiss(report_id: str, request: DismissRequest, principal: Contributor) -> ReportQueue:
    """The report is settled with one of two fixed reasons; the petition is untouched."""
    petition_reports.dismiss(principal, report_id, Dismissal(request.reason), utc_now())
    return reported(principal)


@router.post("/comment-reports/{report_id}/dismiss", response_model=ReportQueue, dependencies=[Changes])
def dismiss_comment_report(report_id: str, request: DismissRequest, principal: Contributor) -> ReportQueue:
    """The same two fixed reasons settle a report about a comment; the comment stays as it is."""
    petition_comments.dismiss(principal, report_id, Dismissal(request.reason), utc_now())
    return reported(principal)


@router.get("/mine", response_model=MyPetitions)
def mine(proof: Phone) -> MyPetitions:
    return MyPetitions(number=proof.hint, petitions=[present.own(p) for p in petitions.mine(proof)])


@router.post("/check", response_model=ScreenResult, dependencies=[Checks])
def check(request: ScreenRequest) -> ScreenResult:
    screened = petition_screen.screen(request.title, request.body)
    return ScreenResult(stop=screened.stop, warning=screened.warning)


@router.post("/ledger", response_model=list[LedgerMatch], dependencies=[Checks])
def draft_ledger(request: LedgerSearchRequest) -> list[LedgerMatch]:
    if request.topic not in TOPICS_BY_ID:
        raise InvalidPetition("Choose a topic from the list.")
    query = petition_ledger.query_for(request.title, request.body, TOPICS_BY_ID[request.topic].label)
    return [LedgerMatch(**asdict(match)) for match in petition_ledger.cached_search(query)]


@router.post("", response_model=OwnPetition, status_code=201, dependencies=[Changes])
def submit(request: Annotated[SubmitRequest, Form()], proof: Phone) -> OwnPetition:
    """A form, so the petition's images arrive with its words. It is published by this call: nobody approves it."""
    _stop_if_screened(request.title, request.body)
    draft = _draft(request, _stored_images(request.images))
    return present.own(petitions.submit(proof, draft, request.show_name, request.name, utc_now()))


def _stop_if_screened(title: str, body: str) -> None:
    """The checks that stop a petition apply again when it is sent; the private-person warning is the creator's to weigh."""
    stop = petition_screen.hard_stop(title, body)
    if stop:
        raise InvalidPetition(stop)


@router.get("/{code}", response_model=PetitionDetail | Tombstone)
def petition(code: str) -> PetitionDetail | Tombstone:
    """A petition, or — where one was removed — the tombstone, which is built from the removal record alone."""
    try:
        standing = petitions.public(code)
    except petitions.PetitionNotFound:
        return _tombstone(code)
    # Counted only for a petition this call has already read publicly, so a removed one carries no count, as it
    # carries no comments.
    return present.detail(standing).model_copy(update={"comments": petition_comments.count_on(standing)})


def _tombstone(code: str) -> Tombstone:
    removed = petitions.find(code)  # raises PetitionNotFound if there is no such petition at all
    removal = petition_removals.latest_removal(removed["$id"])
    if removal is None:
        raise petitions.PetitionNotFound(code)
    return present.tombstone(petition_removals.tombstone(removal))


@router.get("/{code}/ledger", response_model=list[LedgerMatch])
def petition_ledger_matches(code: str) -> list[LedgerMatch]:
    return present.ledger_matches(petitions.public(code))


@router.post("/{code}/edit", response_model=OwnPetition, dependencies=[Changes])
def edit(code: str, request: Annotated[EditRequest, Form()], proof: Phone) -> OwnPetition:
    """A new version of the words, and — for a petition that was removed — its publication again."""
    _stop_if_screened(request.title, request.body)
    draft = _draft(request, _stored_images(request.images, tuple(request.keep_images)))
    return present.own(petitions.edit(code, proof, draft, utc_now()))


@router.post("/{code}/withdraw", response_model=OwnPetition, dependencies=[Changes])
def withdraw(code: str, proof: Phone) -> OwnPetition:
    """The creator closes their own petition. It stays public, closed, with the signatures it has."""
    return present.own(petitions.withdraw(code, proof, utc_now()))


@router.post("/{code}/anonymous", response_model=OwnPetition, dependencies=[Changes])
def anonymous(code: str, proof: Phone) -> OwnPetition:
    return present.own(petitions.make_anonymous(code, proof))


def report_limits(request: Request, code: str) -> None:
    """Two counts: one device can't flood the queue, and one petition can't be buried under reports. Neither hides
    anything — a report never does — so a limit here only keeps the queue readable."""
    refuse_if_over(rate_limit.PETITION_REPORTS, client_address(request))
    refuse_if_over(rate_limit.PETITION_REPORTS_ABOUT_ONE, f"petition:{code}")


@router.post("/{code}/report", response_model=ReportFiled, status_code=201, dependencies=[Depends(report_limits)])
def report(code: str, request: ReportRequest) -> ReportFiled:
    """Anyone, without signing in. The petition stays exactly as it is while a contributor reads this."""
    filed = petition_reports.file_report(code, Ground(request.ground), request.duplicate_of, request.note, utc_now())
    return ReportFiled(message=present.report_received(), reported_at=filed["createdAt"])


@router.post("/{code}/removal", response_model=ReportQueue, dependencies=[Changes])
def remove(code: str, request: RemovalRequest, principal: Contributor, proof: Phone, tasks: BackgroundTasks) -> ReportQueue:
    """A contributor takes a petition down on a named ground. The confirmed phone is what proves they are neither
    the person who started it nor one of its signers."""
    removed = petition_removals.remove(principal, proof, code, Ground(request.ground), request.duplicate_of,
                                       request.note, utc_now())
    tasks.add_task(petition_updates.notify_quietly, removed.petition, Update.REMOVED)
    return reported(principal)


@router.post("/{code}/response", response_model=list[AwaitingResponse])
def respond(code: str, request: ResponseRequest, principal: Mce, tasks: BackgroundTasks) -> list[AwaitingResponse]:
    """The MCE's public response; then the petitions still waiting for one."""
    answer = Response(request.kind, request.text, request.department, tuple(request.documents))
    updated = petition_responses.respond(principal, code, answer, utc_now())
    tasks.add_task(petition_updates.notify_quietly, updated, Update.RESPONDED)
    return responses(principal)


@router.post("/{code}/signatures", response_model=SignResult, dependencies=[Signing])
def sign(code: str, request: SignRequest, proof: Phone, tasks: BackgroundTasks) -> SignResult:
    signed = petition_signatures.sign(code, proof.number, proof.channel, request.show_name, request.name, utc_now())
    if signed.reached:
        tasks.add_task(petition_updates.notify_quietly, signed.petition, Update.THRESHOLD_REACHED)
    return SignResult(added=signed.added, named=signed.named, signatures=signed.petition.get("signatureCount") or 0,
                      threshold=signed.petition.get("threshold"), status=signed.petition["status"],
                      version=version_of(signed.petition))


@router.get("/{code}/signature", response_model=MySignature)
def my_signature(code: str, proof: Phone) -> MySignature:
    return present.my_signature(petition_signatures.my_signature(code, proof.number))


@router.post("/{code}/signature/anonymous", response_model=MySignature, dependencies=[Changes])
def signature_anonymous(code: str, proof: Phone) -> MySignature:
    return present.my_signature(petition_signatures.make_anonymous(code, proof.number))


@router.get("/{code}/names", response_model=NamedSignatures)
def names(
    code: str,
    limit: Annotated[int, Query(ge=1, le=petition_signatures.NAMES_PAGE_MAX)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NamedSignatures:
    rows, total = petition_signatures.named(code, limit, offset)
    return NamedSignatures(names=[present.named_signature(r) for r in rows if r.get("name")], total=total)


def comment_limits(code: str, proof: Phone) -> None:
    """Two counts, as a report's are: one confirmed number can't flood the petitions, and one petition can't be
    buried under comments. The number itself is never a key here — its keyed hash is."""
    refuse_if_over(rate_limit.PETITION_COMMENTS, f"comments:{phone_proof.phone_key(proof.number)}")
    refuse_if_over(rate_limit.PETITION_COMMENTS_ON_ONE, f"petition:{code}")


@router.get("/{code}/comments", response_model=CommentPage)
def comments(
    code: str,
    limit: Annotated[int, Query(ge=1, le=petition_comments.PAGE_MAX)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> CommentPage:
    """Newest first. A removed petition has none to give: they went down with it, and are back when it is."""
    seen, total = petition_comments.on_petition(code, limit, offset)
    return CommentPage(comments=[_comment(said) for said in seen], total=total)


@router.post("/{code}/comments", response_model=Comment, status_code=201, dependencies=[Depends(comment_limits)])
def comment(code: str, request: CommentRequest, proof: Phone) -> Comment:
    """The same confirmed number a signature is given with, and no more stored with the comment than with one."""
    return _comment(petition_comments.add(code, proof, request.name, request.text, utc_now()))


@router.post("/{code}/comments/{comment_id}/report", response_model=ReportFiled, status_code=201,
             dependencies=[Depends(report_limits)])
def report_comment(code: str, comment_id: str, request: CommentReportRequest) -> ReportFiled:
    """Anyone, without signing in. The comment stays exactly as it is while a contributor reads this."""
    filed = petition_comments.file_report(code, comment_id, Ground(request.ground), request.note, utc_now())
    return ReportFiled(message=petition_comments.report_received(), reported_at=filed["createdAt"])


@router.post("/{code}/comments/{comment_id}/removal", response_model=ReportQueue, dependencies=[Changes])
def remove_comment(code: str, comment_id: str, request: CommentRemovalRequest, principal: Contributor) -> ReportQueue:
    """A contributor takes one comment down on a named ground. The petition stays up and so does every other
    comment: it was this comment that was judged, and the ground stands where its words were."""
    petition_comments.remove(principal, code, comment_id, Ground(request.ground), utc_now())
    return reported(principal)
