"""The MCE's public response to a petition that reached its threshold.

One of three: the Assembly will act; it's referred to a department (named);
or the Assembly can't act, and why. Always with a written statement, and
optionally up to three Ledger documents. It is published on the petition's
page as it was given and can't be changed afterwards: the trail keeps the
MCE's name, the page says "the MCE".

A response after the 30 days is still taken, and the page says how many days
late it came. Once answered, the petition takes no more signatures.
"""

from datetime import datetime
from typing import Any

from app.services import petitions
from app.services.auth import Principal
from app.services.locks import record_lock
from app.services.petition_rules import PetitionAction, Response, response_fields


def respond(principal: Principal, code: str, response: Response, now: datetime) -> dict[str, Any]:
    """Publish the MCE's response on the petition; returns the petition as it now stands."""
    petitions.check_documents(response.documents)
    petition = petitions.find(code)
    with record_lock(petition["$id"]):
        petition = petitions.find(code)
        changes = {**response_fields(petition, response, now), "respondedByName": principal.name}
        updated = petitions.update_petition(petition["$id"], changes)
        petitions.record_history(updated, PetitionAction.RESPONDED, petitions.mce_actor(principal), petition["status"],
                                 reason=response.kind)
    return updated
