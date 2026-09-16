"""USSD (Arkesel): the keypad menu. Ask a question, report an issue, check a case, confirm a web code, sign a petition.

A screen holds 160 characters and a session lasts seconds, so:
- the menu's place is kept in Redis under the session ID, for 3 minutes;
- an answer takes 6 to 13 seconds, longer than a screen can wait, so the
  session ends with "your answer is on its way by SMS";
- a report is filed while the citizen waits, for up to 8 seconds. If it takes
  longer, the reference follows by SMS, even if they chose no updates: they
  would otherwise lose it.
The report is read (classified) as soon as it is described, allowed 4 seconds
before the rules decide alone. An emergency (a danger to a person, a fire, an
accident, a flood, a crime) then shows every number to call for it, over as
many screens as they need, before anything else: help first, filing second. A
personal-safety report then shows what to do right now, and is asked only for
its sub-metro, which it may skip, never its electoral area; its Social Welfare
desk is shown once the sub-metro is known. It gets the reference on screen,
updates only if the citizen then says yes, and any SMS about the report says
nothing but the reference. Last, the citizen may ask for the numbers by SMS,
told first that anyone with the phone could see them: nobody gets them without
choosing, and nobody who asks is refused (a phone that already had them three
times today is told so; each is two SMS credits). Reports carry no photos.
Described text that reads as a medical emergency (someone ill or hurt, no one
else to blame) gets the ambulance numbers and is not filed, as on WhatsApp and
menu 4, unless the citizen says to file it anyway. The same services as the web:
report_intake.submit() and rag.answer_question(). "Confirm a web code" proves the
number to a Nokware page that asked for it (phone_proof): the network says who dialled.
"Sign a petition" takes the petition's six-digit number and signs it from the
dialling number, anonymously unless the resident chooses to show a name, after
being told that anyone can see it, including the department it concerns.
"""

import logging
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FilingTimeout
from dataclasses import dataclass
from typing import Any

from app import safety_steps
from app.config import get_settings
from app.contacts import EMERGENCY_TOPICS, short_line
from app.services import (
    channel_intent,
    channel_limits,
    channel_sessions,
    petition_signatures,
    petition_updates,
    petitions,
    phone_proof,
    report_followups,
    report_intake,
    report_store,
)
from app.services.channel_answers import for_sms
from app.services.channel_contacts import call_lines, desk_line, numbers_sms
from app.services.channel_messages import send_sms
from app.services.channel_status import status_text
from app.services.citizen_reports import IntakeChannel, NotificationEvent
from app.services.ledger_documents import utc_now
from app.services.notifications import notify_quietly
from app.services.petition_rules import InvalidPetition, WrongState, check_signable, clean_signer_name, normalise_code
from app.services.rag import AnswerLength, answer_question
from app.services.report_contacts import ContactChoice, InvalidNumber, masked, normalise_phone, save_contact, update_contact
from app.services.report_intake import DESCRIPTION_MIN, Receipt, ReportSubmission
from app.services.report_rules import Classification, ClassificationMethod, InvalidReport, classify, normalise_reference
from app.services.report_taxonomy import Category
from app.services.sms_text import plain
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
MENU = "Nokware - Accra Assembly\n1 Ask a question\n2 Report an issue\n3 Check a case\n4 Medical emergency\n5 Confirm a web code\n6 Sign a petition"
MEDICAL = "Nokware can't file this: it isn't an Assembly matter. Ambulance: 193, 0501 614 877, 0505 982 870. Or call 112."
CONFIRM = "File this report?\n1 File, and SMS me updates\n2 File, no SMS\n0 Cancel"
# Personal safety asks about messages once, after filing, with the reason beside the question. Offering "SMS me
# updates" here as well asked twice — and never turned updates on, since a report read as personal safety waits
# for the citizen's say — so the first offer was misleading as well as repeated.
SEND = "Send this report?\n1 Send\n0 Cancel"
UPDATES_ASK = "SMS updates on it? They never say what it is about.\n1 Yes\n2 No"
NEXT = "\n1 Next"
HELP_HEADING = "In danger now? Call 112. If it fails, try the next number."
MEDICAL_REPORT = ("This sounds like a medical emergency, which Nokware can't send help for. Ambulance: 193, 0501 614 877, "
                  "0505 982 870, or 112.\n1 File it as a report anyway\n0 End")
NUMBERS_OFFER = "Send these numbers by SMS? Anyone with your phone could see them.\n1 Yes\n2 No"
CALL_LIST = "Your call list may show you dialled Nokware: delete it if that is safer."
_filing = ThreadPoolExecutor(max_workers=8, thread_name_prefix="ussd-filing")  # a reading takes two

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
    if choice == "5":
        return con("Enter the 6-digit code shown on the Nokware page:"), {"step": "code"}
    if choice == "6":
        return con("Enter the petition's 6-digit number:"), {"step": "sign_code"}
    return con("Choose 1 to 6.\n" + MENU), state


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


def _pack(lines: list[str]) -> list[str]:
    """Lines on as few screens as hold them, each screen leaving room for its key line."""
    pages: list[str] = []
    page: list[str] = []
    for line in lines:
        if page and len("\n".join([*page, line]) + CONTINUE) > SCREEN_MAX:
            pages.append("\n".join(page))
            page = []
        page.append(line)
    return [*pages, "\n".join(page)] if page else []


def numbers_pages(topic: str) -> list[str]:
    """Every number to call for an emergency, the services that come to you first. Empty for everyday topics."""
    lines = call_lines(topic, None)
    return _pack([HELP_HEADING, *lines]) if lines else []


def help_pages(topic: str, private: bool) -> list[str]:
    """What comes before any question about place: the numbers, then for personal safety what to do now."""
    return numbers_pages(topic) + (_pack(list(safety_steps.STEPS)) if private else [])


def safety_sub_metro_screen() -> str:
    return _numbered("Which sub-metro are you in? (helps reach Social Welfare)", [sub_metros()[i].name for i in _sub_metro_ids()]) + "\n0 Skip"


def _after_help(state: State) -> tuple[Reply, State]:
    if _private(state):
        return con(safety_sub_metro_screen()), {**state, "step": "safety_sub_metro"}
    return con(sub_metro_screen()), {**state, "step": "sub_metro"}


def _help_page(state: State, page: int) -> tuple[Reply, State]:
    pages = help_pages(state["filed"]["topic"], _private(state))
    if page >= len(pages):
        return _after_help(state)
    key = CONTINUE if page == len(pages) - 1 else NEXT
    return con(pages[page] + key), {**state, "step": "help", "page": page}


def _describe(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    description = dial.text.strip()
    if len(description) < DESCRIPTION_MIN:
        return con("Please describe it in a few more words, with where it is:"), state
    started, check = time.monotonic(), _filing.submit(channel_intent.is_medical, description)
    state = {"description": description, "filed": _saved(_read(description))}
    if _medical_now(check, started):
        return con(MEDICAL_REPORT), {**state, "step": "medical"}
    return _help_page(state, 0)  # help first, filing second


def _medical_now(check: "Future[bool]", started: float) -> bool:
    """Whether the text reads as medical, if that is known within the same few seconds as the reading."""
    try:
        return check.result(timeout=max(0.0, started + CLASSIFY_WAIT_SECONDS - time.monotonic()))
    except FilingTimeout:
        return False


def _medical(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    """The model can misread: a citizen who chose to report something can still file it."""
    if dial.text.strip() == "1":
        return _help_page(state, 0)
    return end("Nothing was filed. Ambulance: 193, or call 112."), None


def _help(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    return _help_page(state, state.get("page", 0) + 1)


def _safety_sub_metro(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    """Personal safety: the sub-metro only, and the citizen may skip it. Never the electoral area."""
    choice = dial.text.strip()
    ids = _sub_metro_ids()
    index = _pick(choice, len(ids))
    if choice != "0" and index is None:
        return con("Choose a number from the list, or 0 to skip.\n" + safety_sub_metro_screen()), state
    sub_metro = None if choice == "0" else ids[index]
    desk = desk_line(sub_metro)  # their own desk, now that it is known
    return con(f"{desk}\n{SEND}" if desk else SEND), {**state, "step": "confirm", "sub_metro": sub_metro}


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
        who = " or ".join(short_name(r) for r in case["recipients"])
        offer = {"reference": reference, "topic": case["topic"], "sub_metro": case.get("subMetro"),
                 "case_id": case["$id"], "who": who}
        more = f"More numbers: {_site()}/contacts/emergency"
        return con(f"Reference {reference} received. {more}\n{UPDATES_ASK}"), {"step": "updates", **offer}
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
        slow = "Your report is being filed. Your reference will come by SMS."
        if private:  # the numbers can still be asked for while it files
            offer = {"reference": None, "topic": state["filed"]["topic"], "sub_metro": state.get("sub_metro")}
            return con(f"{slow}\n{NUMBERS_OFFER}"), {"step": "numbers_sms", **offer}
        return end(slow), None
    except (InvalidReport, InvalidNumber) as error:
        return end(str(error)), None


def _confirm(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    choice = dial.text.strip()
    if choice == "0":
        return end("Cancelled. Nothing was filed."), None
    if _private(state):  # sent without the number: it is attached only if they say yes to something
        return _file(dial, state, False, later) if choice == "1" else (con("Choose 1 or 0.\n" + SEND), state)
    if choice not in ("1", "2"):
        return con("Choose 1, 2 or 0.\n" + CONFIRM), state
    # Someone in danger is never turned away by the hourly report limit.
    if not _private(state) and not channel_limits.REPORTS.allow(dial.msisdn, utc_now().timestamp()):
        return end("You've filed several reports this hour. Please try again later."), None
    return _file(dial, state, choice == "1", later)


def _updates(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    """Messages about a personal-safety report, asked once. The number is kept only if they say yes: this is a
    live session on their own phone, so a session that drops before they answer leaves nothing behind."""
    choice = dial.text.strip()
    if choice not in ("1", "2"):
        return con("Choose 1 for updates or 2 for none."), state
    wanted = choice == "1"
    if wanted:
        save_contact(state["case_id"], ContactChoice(normalise_phone(dial.msisdn), None, notify=True, callback_consent=False))
        later(notify_quietly, report_followups.find(state["reference"]), NotificationEvent.SUBMITTED)
    said = "Updates are on." if wanted else "No updates will be sent."
    question = f"{said}\nMay {state['who']} phone you on this number about it?\n1 Yes\n2 No"
    return con(question), {**state, "step": "call", "updates": wanted}


def _offer(state: State) -> State:
    """What the numbers SMS at the end of a personal-safety report needs to know."""
    return {name: state.get(name) for name in ("reference", "topic", "sub_metro")}


def _call(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    """A separate, explicit choice from updates: whether the responders may phone the citizen."""
    choice = dial.text.strip()
    if choice not in ("1", "2"):
        return con("Choose 1 if they may phone you, or 2 if not."), state
    said = "No one will phone you."
    if choice == "1" and state.get("updates"):
        update_contact(state["case_id"], {"callbackConsent": True})
        said = f"Done. {state['who']} may phone you."
    elif choice == "1":  # a call only: the number is kept for that and nothing else
        save_contact(state["case_id"], ContactChoice(normalise_phone(dial.msisdn), None, notify=False, callback_consent=True))
        said = f"Done. {state['who']} may phone you."
    return con(f"{said}\n{NUMBERS_OFFER}"), {**_offer(state), "step": "numbers_sms"}


def _numbers_sms(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    """The citizen's own choice, knowing who else might read their phone: the numbers by SMS, or not."""
    choice = dial.text.strip()
    if choice not in ("1", "2"):
        return con("Choose 1 or 2.\n" + NUMBERS_OFFER), state
    keep = f" Keep your reference {state['reference']}." if state.get("reference") else ""
    if choice == "2":
        return end(f"No SMS sent.{keep}\n{CALL_LIST}"), None
    if not channel_limits.NUMBERS_SMS.allow(dial.msisdn, utc_now().timestamp()):
        return end(f"The numbers were already sent to this phone today.{keep}\n{CALL_LIST}"), None
    later(send_sms, dial.msisdn, numbers_sms(state["topic"], state.get("sub_metro")))
    return end(f"The numbers are on their way by SMS.{keep}\n{CALL_LIST}"), None


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


CODE_REPLIES = {
    phone_proof.Claim.PROVEN: "Your number is confirmed. Go back to the Nokware page to carry on.",
    phone_proof.Claim.NOT_GHANAIAN: "Only Ghanaian mobile numbers can be confirmed.",
    phone_proof.Claim.UNKNOWN: "That code isn't right or has expired: codes last 15 minutes. Get a new one on the page.",
}


def _code(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    if not channel_limits.CODE_CLAIMS.allow(dial.msisdn, utc_now().timestamp()):
        return end("Too many codes this hour. Please try again later."), None
    return end(CODE_REPLIES[phone_proof.claim(dial.text, dial.msisdn, phone_proof.Channel.USSD, utc_now())]), None


TITLE_ON_SCREEN = 70
NAME_PROMPT = ("Your name will be shown on the petition: anyone can see it, including the department it concerns. "
               "Type your name, or 0 to sign anonymously:")


def _signed(dial: Dial, code: str, name: str | None, later: Later) -> tuple[Reply, State | None]:
    try:
        signed = petition_signatures.sign(code, dial.msisdn, phone_proof.Channel.USSD, name is not None, name, utc_now())
    except (petitions.PetitionNotFound, WrongState) as error:
        return end(str(error) if isinstance(error, WrongState) else "No open petition has that number."), None
    if signed.reached:  # this signature sent it to the MCE: its creator is told, after the screen is sent
        later(petition_updates.notify_quietly, signed.petition, petition_updates.Update.THRESHOLD_REACHED)
    if not signed.added:
        return end("This number has already signed this petition."), None
    count = f"{signed.petition.get('signatureCount') or 0} of {signed.petition.get('threshold')} signatures"
    return end(f"Signed{' with your name shown' if signed.named else ' anonymously'}. {count}. Thank you."), None


def _sign_code(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    code = normalise_code(dial.text)
    if code is None:
        return con("A petition number has 6 digits. Try again:"), state
    try:
        petition = petitions.public(code)
        check_signable(petition, utc_now())
    except (petitions.PetitionNotFound, WrongState):
        return end("No open petition has that number. Check it and dial again."), None
    title = petition["title"] if len(petition["title"]) <= TITLE_ON_SCREEN else petition["title"][: TITLE_ON_SCREEN - 3] + "..."
    menu = f"{title}\n1 Sign, name not shown\n2 Sign with my name shown\n0 Cancel"
    return con(menu), {"step": "sign_choice", "code": code}


def _sign_choice(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    choice = dial.text.strip()
    if choice == "1":
        return _signed(dial, state["code"], None, later)
    if choice == "2":
        return con(NAME_PROMPT), {**state, "step": "sign_name"}
    if choice == "0":
        return end("Cancelled. You haven't signed."), None
    return con("Choose 1, 2 or 0."), state


def _sign_name(dial: Dial, state: State, later: Later) -> tuple[Reply, State | None]:
    typed = dial.text.strip()
    if typed == "0":
        return _signed(dial, state["code"], None, later)
    try:
        clean_signer_name(True, typed)
    except InvalidPetition as error:
        return con(f"{error} Type your name, or 0 to sign anonymously:"), state
    return _signed(dial, state["code"], typed, later)


STEPS: dict[str, Callable[[Dial, State, Later], tuple[Reply, State | None]]] = {
    "menu": _menu, "ask": _ask, "describe": _describe, "medical": _medical, "help": _help, "sub_metro": _sub_metro,
    "ward": _ward, "safety_sub_metro": _safety_sub_metro, "confirm": _confirm, "updates": _updates, "call": _call,
    "numbers_sms": _numbers_sms, "check": _check, "code": _code, "sign_code": _sign_code, "sign_choice": _sign_choice, "sign_name": _sign_name,
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
