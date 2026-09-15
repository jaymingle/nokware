"""Petitions: public pages, the creator's own petitions (by a confirmed phone), and the MCE's review.

    GET  /api/petitions/options            topics, areas, thresholds, refusal reasons, ways to confirm a number
    GET  /api/petitions                    published petitions (?group=open|closed, ?topic) and the MCE's moderation record
    GET  /api/petitions/review             MCE: petitions waiting for a decision, closest to publishing automatically first
    GET  /api/petitions/responses          MCE: petitions that reached their threshold, closest to their 30 days first
    GET  /api/petitions/mine               the creator's own petitions (X-Phone-Proof)
    POST /api/petitions/check              the draft's words, checked before it is sent
    POST /api/petitions/ledger             what the Ledger holds on a draft's subject
    POST /api/petitions                    submit a petition for review (X-Phone-Proof)
    GET  /api/petitions/{code}             one published petition
    GET  /api/petitions/{code}/ledger      what the Ledger holds on its subject
    POST /api/petitions/{code}/resubmit    a refused petition, edited (X-Phone-Proof)
    POST /api/petitions/{code}/withdraw    (X-Phone-Proof)
    POST /api/petitions/{code}/anonymous   take the creator's name off it (X-Phone-Proof)
    POST /api/petitions/{code}/decision    MCE: publish, or refuse for a fixed reason
    POST /api/petitions/{code}/response    MCE: the public response to a petition that reached its threshold
    POST /api/petitions/{code}/signatures  sign it, anonymous unless a name is shown (X-Phone-Proof)
    GET  /api/petitions/{code}/signature   whether this number has signed (X-Phone-Proof)
    POST /api/petitions/{code}/signature/anonymous   take the signer's name off (X-Phone-Proof)
    GET  /api/petitions/{code}/names       the names signers chose to show, newest first
"""

from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query

from app.config import get_settings
from app.dependencies import rate_limited, require_roles
from app.routes import petition_presenters as present
from app.schemas.documents import Option
from app.schemas.petitions import (
    AreaOption,
    AwaitingResponse,
    DecisionRequest,
    DraftRequest,
    LedgerMatch,
    LedgerSearchRequest,
    MyPetitions,
    MySignature,
    NamedSignatures,
    OwnPetition,
    PetitionDetail,
    PetitionOptions,
    PetitionPage,
    ResponseRequest,
    ReviewQueue,
    ScreenRequest,
    ScreenResult,
    SignRequest,
    SignResult,
    SubmitRequest,
    Verification,
)
from app.services import (
    petition_ledger,
    petition_responses,
    petition_screen,
    petition_signatures,
    petition_updates,
    petitions,
    phone_proof,
    rate_limit,
)
from app.services.petition_updates import Update
from app.services.auth import Principal, Role
from app.services.ledger_documents import utc_now
from app.services.petition_rules import (
    OPEN_FOR,
    RESPONSE_WINDOW,
    REVIEW_WINDOW,
    Draft,
    InvalidPetition,
    PetitionStatus,
    Response,
    Scope,
    petition_topics,
)
from app.services.report_taxonomy import TOPICS_BY_ID
from app.wards import sub_metros, wards

router = APIRouter(prefix="/api/petitions", tags=["petitions"])
Checks = Depends(rate_limited(rate_limit.PETITION_CHECKS))
Changes = Depends(rate_limited(rate_limit.PETITION_CHANGES))
Signing = Depends(rate_limited(rate_limit.SIGNING))
Mce = Annotated[Principal, Depends(require_roles(Role.MCE))]
PAGE_MAX = 50
GROUPS = {"open": [PetitionStatus.OPEN], "awaiting": [PetitionStatus.AWAITING_RESPONSE], "responded": [PetitionStatus.RESPONDED],
          "closed": [PetitionStatus.CLOSED, PetitionStatus.WITHDRAWN]}


def confirmed_phone(x_phone_proof: Annotated[str | None, Header()] = None) -> phone_proof.Proof:
    """The number a page confirmed, from its sealed proof (401 if missing, altered or expired)."""
    return phone_proof.open_proof(x_phone_proof, utc_now())


Phone = Annotated[phone_proof.Proof, Depends(confirmed_phone)]


def _draft(request: DraftRequest) -> Draft:
    return Draft(request.title, request.body, request.topic, Scope(request.scope), request.ward, request.issue,
                 tuple(request.documents))


@router.get("/options", response_model=PetitionOptions)
def options() -> PetitionOptions:
    settings = get_settings()
    return PetitionOptions(
        topics=[Option(id=t.id, name=t.label) for t in petition_topics()],
        areas=[AreaOption(id=w.id, name=w.name, sub_metro=sub_metros()[w.sub_metro].name) for w in wards().values()],
        threshold_area=settings.petition_threshold_area, threshold_metro=settings.petition_threshold_metro,
        review_hours=int(REVIEW_WINDOW.total_seconds() // 3600), open_days=OPEN_FOR.days, response_days=RESPONSE_WINDOW.days,
        refusal_reasons=present.refusal_reasons(),
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
    return PetitionPage(petitions=[present.card(p) for p in found], total=total,
                        moderation=present.moderation(petitions.moderation_counts()),
                        topics=[Option(id=t.id, name=t.label) for t in petition_topics()])


@router.get("/review", response_model=ReviewQueue)
def review(_: Mce) -> ReviewQueue:
    return ReviewQueue(petitions=[present.review_item(p) for p in petitions.review_queue()],
                       refusal_reasons=present.refusal_reasons())


@router.get("/responses", response_model=list[AwaitingResponse])
def responses(_: Mce) -> list[AwaitingResponse]:
    return [present.awaiting(p) for p in petitions.awaiting_response()]


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


@router.post("", response_model=OwnPetition, dependencies=[Changes])
def submit(request: SubmitRequest, proof: Phone) -> OwnPetition:
    _stop_if_screened(request.title, request.body)
    return present.own(petitions.submit(proof, _draft(request), request.show_name, request.name, utc_now()))


def _stop_if_screened(title: str, body: str) -> None:
    """The checks that stop a petition apply again when it is sent; the private-person warning is the creator's to weigh."""
    stop = petition_screen.hard_stop(title, body)
    if stop:
        raise InvalidPetition(stop)


@router.get("/{code}", response_model=PetitionDetail)
def petition(code: str) -> PetitionDetail:
    return present.detail(petitions.public(code))


@router.get("/{code}/ledger", response_model=list[LedgerMatch])
def petition_ledger_matches(code: str) -> list[LedgerMatch]:
    return present.ledger_matches(petitions.public(code))


@router.post("/{code}/resubmit", response_model=OwnPetition, dependencies=[Changes])
def resubmit(code: str, request: DraftRequest, proof: Phone) -> OwnPetition:
    _stop_if_screened(request.title, request.body)
    return present.own(petitions.resubmit(code, proof, _draft(request), utc_now()))


@router.post("/{code}/withdraw", response_model=OwnPetition, dependencies=[Changes])
def withdraw(code: str, proof: Phone) -> OwnPetition:
    return present.own(petitions.withdraw(code, proof, utc_now()))


@router.post("/{code}/anonymous", response_model=OwnPetition, dependencies=[Changes])
def anonymous(code: str, proof: Phone) -> OwnPetition:
    return present.own(petitions.make_anonymous(code, proof))


@router.post("/{code}/decision", response_model=ReviewQueue)
def decide(code: str, request: DecisionRequest, principal: Mce, tasks: BackgroundTasks) -> ReviewQueue:
    """The decision, then the queue as it now stands. The creator is told after the answer is sent."""
    publish = request.decision == "publish"
    updated = petitions.decide(principal, code, publish, request.reason, request.note, request.duplicate_of, utc_now())
    tasks.add_task(petition_updates.notify_quietly, updated, Update.PUBLISHED if publish else Update.REFUSED)
    return review(principal)


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
    if signed.reached:  # this signature sent it to the MCE
        tasks.add_task(petition_updates.notify_quietly, signed.petition, Update.THRESHOLD_REACHED)
    return SignResult(added=signed.added, named=signed.named, signatures=signed.petition.get("signatureCount") or 0,
                      threshold=signed.petition.get("threshold"), status=signed.petition["status"])


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
