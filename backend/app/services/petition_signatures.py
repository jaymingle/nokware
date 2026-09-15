"""Signing a petition: one signature per confirmed Ghanaian number per petition.

A signature holds no phone number. It holds a keyed hash of the number and the
petition together (signerKey), under a unique index, so the same number can't
sign twice, and it can't be matched across petitions: no one can list what a
number has signed. The signer is anonymous unless they choose to show their
name, which is then public, beside the signature. They can take it off later,
by confirming the same number.

The count is recounted after every signature under the petition's lock, and the
signature that reaches the threshold sends the petition to the MCE, who then
has 30 days to respond publicly.

The count is of confirmed numbers, not of people: someone with several SIM
cards can sign once with each. The README says so.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from appwrite.exception import AppwriteException
from appwrite.id import ID
from appwrite.query import Query

from app.services import channel_limits, petitions
from app.services.appwrite_client import DATABASE_ID, as_record, get_databases
from app.services.locks import record_lock
from app.services.petition_rules import (
    PetitionAction,
    PetitionStatus,
    WrongState,
    check_signable,
    clean_signer_name,
    threshold_fields,
)
from app.services.phone_proof import Channel, keyed_hash

logger = logging.getLogger(__name__)

SIGNATURES_COLLECTION = "petition_signatures"
NAMES_PAGE_MAX = 100


@dataclass(frozen=True)
class Signed:
    petition: dict[str, Any]
    added: bool  # False: this number had already signed
    named: bool
    reached: bool  # this signature reached the threshold and sent the petition to the MCE


def signer_key(petition_id: str, number: str) -> str:
    """A number's signature on one petition: the same number on another petition gives an unrelated key."""
    return keyed_hash(f"signature:{petition_id}:{number}")


def _store(petition_id: str, key: str, name: str | None, channel: Channel, now: datetime) -> bool:
    data = {"petitionId": petition_id, "signerKey": key, "named": name is not None, "name": name,
            "channel": channel.value, "createdAt": now.isoformat()}
    try:
        get_databases().create_document(DATABASE_ID, SIGNATURES_COLLECTION, ID.unique(), data)
    except AppwriteException as exc:
        if exc.code == 409:  # the unique index: this number has signed already
            return False
        raise
    return True


def total(petition_id: str) -> int:
    listing = get_databases().list_documents(
        DATABASE_ID, SIGNATURES_COLLECTION, queries=[Query.equal("petitionId", petition_id), Query.limit(1)])
    return int(listing.total)


def _count(petition: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Recount, and send the petition to the MCE if this signature reached its threshold."""
    changes = threshold_fields(petition, total(petition["$id"]), now)
    updated = petitions.update_petition(petition["$id"], changes)
    if changes.get("status") == PetitionStatus.AWAITING_RESPONSE:
        petitions.record_history(updated, PetitionAction.THRESHOLD_REACHED, petitions.SYSTEM, petition["status"])
        logger.info("Petition %s reached its %s signatures and went to the MCE", updated["code"], updated.get("threshold"))
    return updated


def sign(code: str, number: str, channel: Channel, show_name: bool, name: str | None, now: datetime) -> Signed:
    """Sign a published, still-open petition with a confirmed number."""
    shown = clean_signer_name(show_name, name)
    petition = petitions.public(code)
    check_signable(petition, now)
    if not channel_limits.SIGNATURES.allow(number, now.timestamp()):
        raise WrongState("This number has signed as many petitions as it can today. Try again tomorrow.")
    with record_lock(petition["$id"]):
        petition = petitions.public(code)
        check_signable(petition, now)
        added = _store(petition["$id"], signer_key(petition["$id"], number), shown, channel, now)
        updated = _count(petition, now) if added else petition
    reached = petition["status"] == PetitionStatus.OPEN and updated["status"] == PetitionStatus.AWAITING_RESPONSE
    return Signed(updated, added, shown is not None, reached)


def _mine(petition_id: str, number: str) -> dict[str, Any] | None:
    listing = get_databases().list_documents(DATABASE_ID, SIGNATURES_COLLECTION, queries=[
        Query.equal("signerKey", signer_key(petition_id, number)), Query.limit(1)])
    return as_record(listing.documents[0]) if listing.documents else None


def my_signature(code: str, number: str) -> dict[str, Any] | None:
    """This number's signature on the petition, if it has signed."""
    return _mine(petitions.public(code)["$id"], number)


def make_anonymous(code: str, number: str) -> dict[str, Any] | None:
    """Take the signer's name off their signature. It still counts."""
    signature = my_signature(code, number)
    if signature and signature.get("named"):
        changes = {"named": False, "name": None}
        get_databases().update_document(DATABASE_ID, SIGNATURES_COLLECTION, signature["$id"], changes)
        return {**signature, **changes}
    return signature


def named(code: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    """The names signers chose to show, newest first, and how many there are."""
    petition = petitions.public(code)
    listing = get_databases().list_documents(DATABASE_ID, SIGNATURES_COLLECTION, queries=[
        Query.equal("petitionId", petition["$id"]), Query.equal("named", True), Query.select(["name", "createdAt"]),
        Query.order_desc("createdAt"), Query.limit(min(limit, NAMES_PAGE_MAX)), Query.offset(offset)])
    return [as_record(d) for d in listing.documents], int(listing.total)
