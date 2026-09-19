"""The MCE's public response to a petition that reached its threshold, and the petitioner's reply to it.

Published as given and never changed afterwards: the trail keeps the MCE's name, the page says "the MCE". A late
response is still taken, and the page says how late it came.

The person who started the petition may answer that response once, in the same place the public reads it, proving
the number they started it with. One reply is enough and is all there is: a petition's page is a record of what
was asked and what was answered, not a thread, and a second round would turn the page into an argument nobody is
obliged to read. The reply is kept on the petition beside the response, so the two are read and removed together.
"""

from datetime import datetime
from typing import Any

from app.services import petitions
from app.services.auth import Principal
from app.services.locks import record_lock
from app.services.petition_rules import (
    REPLY_MAX,
    PetitionAction,
    Response,
    check_repliable,
    reply_fields,
    response_fields,
)
from app.services.petition_screen import Refusals, screened
from app.services.phone_proof import Proof

REFUSALS = Refusals(empty="petition.reply.empty", too_long="petition.reply.too_long",
                    personal_data="petition.reply.personal_data", private_individual="petition.reply.private_individual")


def respond(principal: Principal, code: str, response: Response, now: datetime) -> dict[str, Any]:
    petitions.check_documents(response.documents)
    petition = petitions.find(code)
    with record_lock(petition["$id"]):
        petition = petitions.find(code)
        changes = {**response_fields(petition, response, now), "respondedByName": principal.name}
        updated = petitions.update_petition(petition["$id"], changes)
        petitions.record_history(updated, PetitionAction.RESPONDED, petitions.mce_actor(principal), petition["status"],
                                 reason=response.kind)
    return updated


def clean_reply(text: str) -> str:
    """The reply as it will be stored, or a refusal saying why it can't be, in the words the creator reads."""
    return screened(text, REPLY_MAX, REFUSALS)


def reply(code: str, proof: Proof, text: str, now: datetime) -> dict[str, Any]:
    """The creator answers the MCE, on the same confirmed number every other action on their petition takes.
    Anyone else's petition is simply not found, as it is for an edit or a withdrawal."""
    said = clean_reply(text)
    petition = petitions.owned(code, proof)
    with record_lock(petition["$id"]):
        petition = petitions.owned(code, proof)
        check_repliable(petition)
        updated = petitions.update_petition(petition["$id"], reply_fields(said, now))
        petitions.record_history(updated, PetitionAction.CREATOR_REPLIED, petitions.CREATOR, petition["status"])
    return updated
