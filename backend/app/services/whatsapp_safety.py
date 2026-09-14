"""After a personal-safety report is filed on WhatsApp: who has it, and the choices it offers for an hour.

The receipt says who has the report and offers, each a separate explicit choice:
- CALL: the Police or Social Welfare may phone the citizen on this number (apart from updates);
- PLACE: say exactly where they are, so help can come (report_locations: the one exception to
  the coarse-location rule, only on this opt-in). The message that carried it is then deleted
  from Twilio's log, and it never passes through Redis;
- REMOVE: delete that location again, confirmed only once it is gone;
- YES: updates here, which never say what the report is about.
Anything else is a new message. The choices last an hour, like the updates choice on the web.
"""

from typing import Any

from app.services import channel_sessions, report_followups, report_locations, whatsapp_reply
from app.services.ledger_documents import utc_now
from app.services.report_contacts import update_contact
from app.services.report_intake import Receipt
from app.services.whatsapp import WhatsAppNotConfigured, twilio
from app.services.workflow import NotAllowed
from app.teams import short_name

AFTER_SECONDS = 60 * 60
PLACE_MIN = 3
LOCATION_TERMS = (
    "Only the Police and Social Welfare handling your report can see it: never the public dashboard, never the "
    "MCE. It is deleted 30 days after the case closes, or at once if you reply *REMOVE*."
)
State = dict[str, Any]


def _names(recipients: list[str]) -> list[str]:
    return [short_name(r) for r in recipients]


def receipt_text(receipt: Receipt) -> str:
    case = receipt.case
    names = _names(case["recipients"])
    choices = [f"*CALL* for {' or '.join(names)} to phone you on this number",
               "*PLACE* to tell them exactly where you are, so help can come"]
    if receipt.preferences_token:
        choices.append("*YES* for updates here (they never say what the report is about)")
    return (f"This has gone to {' and '.join(names)}. Your reference is *{case['reference']}*.\n\n"
            "If you want, reply:\n" + "\n".join(choices) + "\nYou can reply to these within the hour.")


def after_filing(number: str, receipt: Receipt) -> None:
    """Keep the hour's choices, and send the receipt."""
    state = {"step": "after", "reference": receipt.case["reference"], "case_id": receipt.case["$id"],
             "recipients": receipt.case["recipients"], "token": receipt.preferences_token}
    channel_sessions.save("whatsapp", number, state, AFTER_SECONDS)
    whatsapp_reply.reply(number, receipt_text(receipt))


def _updates(number: str, state: State, wanted: bool) -> None:
    if not state.get("token"):
        whatsapp_reply.reply(number, "Updates can't be changed now.")
        return
    try:
        choice = report_followups.Preferences(notify=wanted, callback_consent=False)
        report_followups.set_preferences(state["reference"], state["token"], choice, utc_now())
    except NotAllowed:
        whatsapp_reply.reply(number, "Updates can't be changed now.")
        return
    channel_sessions.save("whatsapp", number, {**state, "token": None}, AFTER_SECONDS)
    whatsapp_reply.reply(number, f"Updates are on for {state['reference']}." if wanted else "No updates will be sent.")


def _call(number: str, state: State) -> None:
    update_contact(state["case_id"], {"callbackConsent": True})
    who = " or ".join(_names(state["recipients"]))
    whatsapp_reply.reply(number, f"Done. {who} may phone you on this number about this report.")


def _remove(number: str, state: State) -> None:
    if report_locations.remove(state["case_id"]):
        whatsapp_reply.reply(number, "Your location has been deleted. The Police and Social Welfare can no longer see it.")
    else:
        whatsapp_reply.reply(number, "Your location couldn't be deleted just now. Please reply *REMOVE* again in a minute.")


def after_step(inbound: Any, state: State) -> bool:
    """One of the hour's choices; anything else is handled as a new message."""
    choice = inbound.text.strip().lower()
    if choice in ("yes", "y", "no", "n"):
        _updates(inbound.number, state, choice in ("yes", "y"))
    elif choice == "call":
        _call(inbound.number, state)
    elif choice == "place":
        channel_sessions.save("whatsapp", inbound.number, {**state, "step": "place"}, AFTER_SECONDS)
        whatsapp_reply.reply(inbound.number, "Send your location with WhatsApp's location button, or type the house address "
                             f"or a landmark. {LOCATION_TERMS}\nReply *0* to leave it.")
    elif choice == "remove":
        _remove(inbound.number, state)
    else:
        return False
    return True


def _forget_message(message_sid: str) -> None:
    """The message that carried the location leaves Twilio's log too."""
    try:
        twilio().delete_message(message_sid)
    except WhatsAppNotConfigured:
        pass


def place_step(inbound: Any, state: State) -> bool:
    """The location itself: a pin from the location button, or a typed address. 0 leaves it."""
    text = inbound.text.strip()
    back = {**state, "step": "after"}
    if text == "0":
        channel_sessions.save("whatsapp", inbound.number, back, AFTER_SECONDS)
        whatsapp_reply.reply(inbound.number, "No location was shared.")
        return True
    pinned = inbound.latitude is not None and inbound.longitude is not None
    if not pinned and len(text) < PLACE_MIN:
        whatsapp_reply.reply(inbound.number, "Send your location with WhatsApp's location button, or type the address. Reply *0* to leave it.")
        return True
    report_locations.share(state["case_id"], inbound.place if pinned else text, inbound.latitude, inbound.longitude, utc_now())
    _forget_message(inbound.message_sid)
    channel_sessions.save("whatsapp", inbound.number, back, AFTER_SECONDS)
    whatsapp_reply.reply(inbound.number, "Saved. Only the Police and Social Welfare handling your report can see it, and your status "
                         "page shows each time they open it. Reply *REMOVE* to delete it.")
    return True
