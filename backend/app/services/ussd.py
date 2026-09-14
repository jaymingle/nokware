"""USSD (Arkesel): the keypad menu. Ask a question, report an issue, check a case.

A screen holds 160 characters and a session lasts seconds, so:
- the menu's place is kept in Redis under the session ID, for 3 minutes;
- an answer takes 6 to 13 seconds, longer than a screen can wait, so the
  session ends with "your answer is on its way by SMS";
- a report is filed while the citizen waits, for up to 8 seconds. If it takes
  longer, the reference follows by SMS, even if they chose no updates: they
  would otherwise lose it.
The report is read (classified) as soon as it is described, allowed 4 seconds
before the rules decide alone. An emergency (a danger to a person, a fire, a
flood, a crime) then shows two numbers per service to try, before anything
else. A personal-safety report is asked only for its sub-metro, which it may
skip, never its electoral area; it gets the reference on screen, updates only
if the citizen then says yes, and any SMS about it says nothing but the
reference. Reports carry no photos. The same services as the web:
report_intake.submit() and rag.answer_question().
"""

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FilingTimeout
from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.contacts import EMERGENCY_TOPICS, short_line
from app.services import channel_limits, channel_sessions, report_followups, report_intake, report_store
from app.services.channel_answers import for_sms
from app.services.channel_messages import send_sms
from app.services.channel_status import status_text
from app.services.citizen_reports import IntakeChannel, NotificationEvent
from app.services.ledger_documents import utc_now
from app.services.notifications import notify_quietly
from app.services.rag import AnswerLength, answer_question
from app.services.report_contacts import InvalidNumber, masked, update_contact
from app.services.report_intake import DESCRIPTION_MIN, Receipt, ReportSubmission
from app.services.report_rules import Classification, ClassificationMethod, InvalidReport, classify, normalise_reference
from app.services.report_taxonomy import Category
from app.services.sms_text import plain
from app.services.workflow import NotAllowed
from app.teams import short_name
from app.wards import sub_metros, wards

logger = logging.getLogger(__name__)

SESSION_SECONDS = 180
FILING_WAIT_SECONDS = 8.0
CLASSIFY_WAIT_SECONDS = 4.0
CONTINUE = "\n1 Continue"
SCREEN_MAX = 160
QUESTION_MIN = 5
WHO_MAX = 40  # longer office names give way to a count, so the receipt keeps its last words
MENU = "Nokware - Accra Assembly\n1 Ask a question\n2 Report an issue\n3 Check a case\n4 Medical emergency"
MEDICAL = "Nokware can't file this: it isn't an Assembly matter. Ambulance: 193, 0501 614 877, 0505 982 870. Or call 112."
CONFIRM = "File this report?\n1 File, and SMS me updates\n2 File, no SMS\n0 Cancel"
_filing = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ussd-filing")

Later = Callable[..., None]  # runs work after the screen is sent (FastAPI's BackgroundTasks.add_task)
State = dict[str, Any]


@dataclass(frozen=True)
class Reply:
    message: str
    more: bool  # Arkesel's continueSession: another screen follows


@dataclass(frozen=True)
class Dial:
    session_id: str
    msisdn: str  # +233...
    text: str
    new: bool


def _screen(text: str) -> str:
    text = plain(text)
    return text if len(text) <= SCREEN_MAX else text[: SCREEN_MAX - 3].rstrip() + "..."


def con(text: str) -> Reply:
    return Reply(_screen(text), True)


def end(text: str) -> Reply:
    return Reply(_screen(text), False)


def _numbered(title: str, names: list[str]) -> str:
    return title + "\n" + "\n".join(f"{position} {name}" for position, name in enumerate(names, 1))


def _pick(text: str, count: int) -> int | None:
    """The 0-based choice from a numbered list, or None if the reply isn't one of its numbers."""
    choice = text.strip()
    return int(choice) - 1 if choice.isdigit() and 1 <= int(choice) <= count else None


def _sub_metro_ids() -> list[str]:
    return list(sub_metros())


def _ward_ids(sub_metro: str) -> list[str]:
    return [ward.id for ward in wards().values() if ward.sub_metro == sub_metro]


def sub_metro_screen() -> str:
    return _numbered("Which sub-metro is it in?", [sub_metros()[i].name for i in _sub_metro_ids()])


def ward_screen(sub_metro: str) -> str:
    return _numbered("Which electoral area?", [wards()[i].name for i in _ward_ids(sub_metro)])


def _site() -> str:
    return get_settings().public_site_url.rstrip("/")


def answer_by_sms(msisdn: str, question: str) -> None:
    """After the screen has closed: answer the question and send it as one SMS of two pages at most."""
    try:
        text = for_sms(answer_question(question, AnswerLength.SMS), _site())
    except Exception:
        logger.exception("Answering a USSD question for %s failed", masked(msisdn))
        text = "Nokware: sorry, we couldn't answer your question just now. Please try again later."
    send_sms(msisdn, text)


def _menu(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    choice = dial.text.strip()
    if choice == "1":
        return con("Type your question. The answer comes by SMS."), {"step": "ask"}
    if choice == "2":
        return con("Describe the problem and where it is (a street or a landmark):"), {"step": "describe"}
    if choice == "3":
        return con("Enter your case reference, e.g. K7QM-4TXP:"), {"step": "check"}
    if choice == "4":  # not the Assembly's to act on, but the numbers cost nothing to give
        return end(MEDICAL), None
    return con("Choose 1 to 4.\n" + MENU), state


def _ask(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    question = dial.text.strip()
    if len(question) < QUESTION_MIN:
        return con("Type your question in a few words:"), state
    if not channel_limits.SMS_ANSWERS.allow(dial.msisdn, utc_now().timestamp()):
        return end(f"You've had today's answers by SMS. Ask again tomorrow, or at {_site()}/ask"), None
    later(answer_by_sms, dial.msisdn, question)
    return end("Thank you. Your answer is on its way by SMS."), None


def _read(description: str) -> Classification:
    """How the report will be filed, within a few seconds: past that, the rules alone (whose danger screen
    still catches a report about a person), so a slow model never costs the citizen their session."""
    reading = _filing.submit(report_intake.read_report, description)
    try:
        return reading.result(timeout=CLASSIFY_WAIT_SECONDS)
    except FilingTimeout:
        return classify(description, None, None)


def _saved(filed: Classification) -> dict[str, Any]:
    return {"category": filed.category.value, "topic": filed.topic, "severity": filed.severity,
            "recipients": list(filed.recipients), "method": filed.method.value}


def _classification(state: State) -> Classification:
    saved = state["filed"]
    return Classification(Category(saved["category"]), saved["topic"], saved["severity"], tuple(saved["recipients"]),
                          ClassificationMethod(saved["method"]))


def _private(state: State) -> bool:
    return state["filed"]["category"] == Category.PERSONAL_SAFETY


def numbers_screen(topic: str) -> str:
    """Two numbers per service to try now, and where the rest are, then a key to go on."""
    numbers = short_line(topic, None)
    more = f"\nMore numbers: {_site()}/contacts/emergency"
    body = numbers + more if len(numbers + more + CONTINUE) <= SCREEN_MAX else numbers
    return body + CONTINUE


def safety_sub_metro_screen() -> str:
    return _numbered("Which sub-metro are you in? (helps reach Social Welfare)", [sub_metros()[i].name for i in _sub_metro_ids()]) + "\n0 Skip"


def _after_help(state: State) -> tuple[Reply, State]:
    if _private(state):
        return con(safety_sub_metro_screen()), {**state, "step": "safety_sub_metro"}
    return con(sub_metro_screen()), {**state, "step": "sub_metro"}


def _describe(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    description = dial.text.strip()
    if len(description) < DESCRIPTION_MIN:
        return con("Please describe it in a few more words, with where it is:"), state
    filed = _read(description)
    state = {"description": description, "filed": _saved(filed)}
    if filed.topic in EMERGENCY_TOPICS:  # the numbers first: a danger to a person, a fire, a flood, a crime
        return con(numbers_screen(filed.topic)), {**state, "step": "help"}
    return _after_help(state)


def _help(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    return _after_help(state)


def _safety_sub_metro(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    """Personal safety: the sub-metro only, and the citizen may skip it. Never the electoral area."""
    choice = dial.text.strip()
    ids = _sub_metro_ids()
    index = _pick(choice, len(ids))
    if choice != "0" and index is None:
        return con("Choose a number from the list, or 0 to skip.\n" + safety_sub_metro_screen()), state
    return con(CONFIRM), {**state, "step": "confirm", "sub_metro": None if choice == "0" else ids[index]}


def _sub_metro(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    ids = _sub_metro_ids()
    index = _pick(dial.text, len(ids))
    if index is None:
        return con("Choose a number from the list.\n" + sub_metro_screen()), state
    return con(ward_screen(ids[index])), {**state, "step": "ward", "sub_metro": ids[index]}


def _ward(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    ids = _ward_ids(state["sub_metro"])
    index = _pick(dial.text, len(ids))
    if index is None:
        return con("Choose a number from the list.\n" + ward_screen(state["sub_metro"])), state
    return con(CONFIRM), {**state, "step": "confirm", "ward": ids[index]}


def _receipt(receipt: Receipt, later: Later) -> tuple[Reply, State | None]:
    """The screen after filing: the reference, who has it, and what happens next."""
    case = receipt.case
    reference = case["reference"]
    if receipt.messages_on:
        later(notify_quietly, case, NotificationEvent.SUBMITTED)
    if case["isSensitive"]:  # the numbers came first; the rest of them are on the contacts page
        more = f"More numbers: {_site()}/contacts/emergency"
        if receipt.preferences_token:  # a number was given: ask about updates, once
            question = f"Reference {reference} received. {more}\nSMS updates on it? They never say what it is about.\n1 Yes\n2 No"
            return con(question), {"step": "updates", "reference": reference, "token": receipt.preferences_token}
        return end(f"Reference {reference} received. {more}"), None
    names = [short_name(r) for r in case["recipients"]]
    who = " and ".join(names) if len(" and ".join(names)) <= WHO_MAX else f"{len(names)} offices"
    emergency = f" {short_line(case['topic'], None).split('. ')[0]}." if case["topic"] in EMERGENCY_TOPICS else ""
    updates = " We'll SMS you when it's resolved." if receipt.messages_on else ""
    return end(f"Report {reference} filed with {who}.{emergency}{updates} Keep this reference."), None


def _reference_later(filing: "Future[Receipt]", msisdn: str) -> None:
    """A filing that outlasted the screen: send its reference (neutral for personal safety) or say it failed."""
    try:
        receipt = filing.result()
    except Exception:
        logger.exception("A slow USSD filing for %s failed", masked(msisdn))
        send_sms(msisdn, "Nokware: sorry, your report couldn't be filed. Please dial again.")
        return
    if receipt.messages_on:  # the "received" message carries the reference
        notify_quietly(receipt.case, NotificationEvent.SUBMITTED)
        return
    case = receipt.case
    if case["isSensitive"]:
        send_sms(msisdn, f"Nokware: reference {case['reference']} received.")
        return
    numbers = f" If anyone is in danger: {short_line(case['topic'], None)}" if case["topic"] in EMERGENCY_TOPICS else ""
    send_sms(msisdn, f"Nokware: your report is filed. Reference {case['reference']}.{numbers}")


def _file(dial: Dial, state: State, updates: bool, later: Later) -> tuple[Reply, State | None]:
    private = _private(state)
    submission = ReportSubmission(
        description=state["description"], ward=None if private else state["ward"],
        sub_metro=state.get("sub_metro") if private else None, safety_topic=None,
        phone=dial.msisdn if updates else None, whatsapp=None, notify=updates, callback_consent=False,
        channel=IntakeChannel.USSD,
    )
    filing = _filing.submit(report_intake.submit, submission, [], utc_now(), _classification(state))
    try:
        return _receipt(filing.result(timeout=FILING_WAIT_SECONDS), later)
    except FilingTimeout:
        filing.add_done_callback(lambda done: _reference_later(done, dial.msisdn))
        return end("Your report is being filed. Your reference will come by SMS."), None
    except (InvalidReport, InvalidNumber) as error:
        return end(str(error)), None


def _confirm(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    choice = dial.text.strip()
    if choice == "0":
        return end("Cancelled. Nothing was filed."), None
    if choice not in ("1", "2"):
        return con("Choose 1, 2 or 0.\n" + CONFIRM), state
    if not channel_limits.REPORTS.allow(dial.msisdn, utc_now().timestamp()):
        return end("You've filed several reports this hour. Please try again later."), None
    return _file(dial, state, choice == "1", later)


def _updates(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    choice = dial.text.strip()
    if choice not in ("1", "2"):
        return con("Choose 1 for updates or 2 for none."), state
    wanted = choice == "1"
    preferences = report_followups.Preferences(notify=wanted, callback_consent=False)
    try:
        case, messages_on = report_followups.set_preferences(state["reference"], state["token"], preferences, utc_now())
    except NotAllowed:  # the one-time choice was already made, or its hour is up
        return end("That choice can't be changed now. Keep your reference."), None
    if messages_on:
        later(notify_quietly, case, NotificationEvent.SUBMITTED)
    who = " or ".join(short_name(r) for r in case["recipients"])
    said = "Updates are on." if wanted else "No updates will be sent."
    question = f"{said}\nMay {who} phone you on this number about it?\n1 Yes\n2 No"
    return con(question), {"step": "call", "case_id": case["$id"], "who": who}


def _call(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    """A separate, explicit choice from updates: whether the responders may phone the citizen."""
    choice = dial.text.strip()
    if choice not in ("1", "2"):
        return con("Choose 1 if they may phone you, or 2 if not."), state
    if choice == "1":
        update_contact(state["case_id"], {"callbackConsent": True})
        return end(f"Done. {state['who']} may phone you. Keep your reference."), None
    return end("No one will phone you. Keep your reference."), None


def _check(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    reference = normalise_reference(dial.text)
    if reference is None:
        return con("That isn't a reference. It looks like K7QM-4TXP. Try again:"), state
    if not channel_limits.LOOKUPS.allow(dial.msisdn, utc_now().timestamp()):
        return end("Too many lookups this hour. Please try again later."), None
    try:
        case = report_followups.find(reference)
    except report_followups.CaseNotFound:
        return end(f"No case has the reference {reference}. Check it and dial again."), None
    status = report_followups.public_status(case, report_store.assignments_for(case["$id"]), utc_now())
    return end(status_text(status, _site(), compact=True)), None


STEPS: dict[str, Callable[[Dial, State, Later], tuple[Reply, State | None]]] = {
    "menu": _menu, "ask": _ask, "describe": _describe, "help": _help, "sub_metro": _sub_metro, "ward": _ward,
    "safety_sub_metro": _safety_sub_metro, "confirm": _confirm, "updates": _updates, "call": _call, "check": _check,
}


def respond(dial: Dial, later: Later) -> Reply:
    """The next screen for one keypress (or the opening dial) in a USSD session."""
    if dial.new:
        channel_sessions.save("ussd", dial.session_id, {"step": "menu"}, SESSION_SECONDS)
        return con(MENU)
    state = channel_sessions.load("ussd", dial.session_id)
    step = STEPS.get(state.get("step", "")) if state else None
    if state is None or step is None:  # expired, or left by an older version of this menu
        channel_sessions.clear("ussd", dial.session_id)
        return end("Your session ended. Please dial again.")
    reply, next_state = step(dial, state, later)
    if reply.more and next_state is not None:
        channel_sessions.save("ussd", dial.session_id, next_state, SESSION_SECONDS)
    else:
        channel_sessions.clear("ussd", dial.session_id)
    return reply
