"""Confirming a phone number from a web page. No sign-in.

The secret travels in the body, never the address, so it stays out of access logs.
"""

from fastapi import APIRouter, Depends

from app.dependencies import rate_limited
from app.schemas.petitions import ChallengeRequest, ChallengeResult, ChallengeStatus, SmsCodeRequest, SmsCodeSent, SmsConfirmRequest
from app.services import phone_proof, rate_limit
from app.services.ledger_documents import utc_now

router = APIRouter(prefix="/api/phone", tags=["phone"])
Challenges = Depends(rate_limited(rate_limit.PHONE_CHALLENGES))
Polls = Depends(rate_limited(rate_limit.PHONE_POLLS))


def _status(held: phone_proof.ChallengeState) -> ChallengeStatus:
    if held.state != "proven" or not held.proof:
        return ChallengeStatus(state="expired" if held.state == "expired" else "waiting", proof=None, number=None, expires_at=None)
    proof = phone_proof.open_proof(held.proof, utc_now())
    return ChallengeStatus(state="proven", proof=held.proof, number=proof.hint, expires_at=proof.expires_at.isoformat())


@router.post("/challenges", response_model=ChallengeResult, dependencies=[Challenges])
def new_challenge() -> ChallengeResult:
    challenge = phone_proof.new_challenge()
    return ChallengeResult(challenge=challenge.secret, code=challenge.code, expires_in=challenge.expires_in,
                           whatsapp_url=phone_proof.whatsapp_link(challenge.code), ussd_code=phone_proof.ussd_code(),
                           sms=phone_proof.sms_available())


@router.post("/challenges/status", response_model=ChallengeStatus, dependencies=[Polls])
def challenge_status(request: ChallengeRequest) -> ChallengeStatus:
    return _status(phone_proof.state(request.challenge))


@router.post("/challenges/sms", response_model=SmsCodeSent, dependencies=[Challenges])
def sms_code(request: SmsCodeRequest) -> SmsCodeSent:
    return SmsCodeSent(sent_to=phone_proof.send_sms_code(request.challenge, request.phone, utc_now()))


@router.post("/challenges/sms/confirm", response_model=ChallengeStatus, dependencies=[Challenges])
def sms_confirm(request: SmsConfirmRequest) -> ChallengeStatus:
    return _status(phone_proof.confirm_sms_code(request.challenge, request.code, utc_now()))
