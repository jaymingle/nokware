"""The MCE's public response to a petition that reached its threshold.

Published as given and never changed afterwards: the trail keeps the MCE's name, the page says "the MCE". A late
response is still taken, and the page says how late it came.
"""

from datetime import datetime
from typing import Any

from app.services import petitions
from app.services.auth import Principal
from app.services.locks import record_lock
from app.services.petition_rules import PetitionAction, Response, response_fields


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
