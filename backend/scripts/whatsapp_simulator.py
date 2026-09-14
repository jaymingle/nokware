"""A WhatsApp phone in the terminal: sends Twilio-signed webhooks to the API, as Twilio would.

Each message is signed with TWILIO_AUTH_TOKEN for PUBLIC_API_URL (the address
Twilio calls), then posted to --url. Replies go wherever the API sends them:
with WHATSAPP_PROVIDER=log they only appear in the API's log; with
WHATSAPP_PROVIDER=twilio they are real WhatsApp messages, and Twilio charges
for each. Photos can't be simulated: they need a real Twilio media link.
A pin from WhatsApp's location button can (--pin, sent after any messages).

    backend/.venv/bin/python backend/scripts/whatsapp_simulator.py --from +233XXXXXXXXX --url http://localhost:8001 "Hello"
    backend/.venv/bin/python backend/scripts/whatsapp_simulator.py --from +233XXXXXXXXX --pin 5.567,-0.235 --place "Kaneshie Market"
"""

import argparse
import sys
import uuid
from pathlib import Path

import httpx
from dotenv import dotenv_values
from twilio.request_validator import RequestValidator

ENV = Path(__file__).resolve().parents[1] / ".env"
PATH = "/api/channels/whatsapp"


def _forms(args: argparse.Namespace, to: str) -> list[tuple[str, dict[str, str]]]:
    """Twilio's form fields for each message in turn, then the pin; with a label to print for each."""
    base = {"From": f"whatsapp:{args.sender}", "To": to, "NumMedia": "0"}
    forms = [(text, {**base, "Body": text}) for text in args.messages]
    if args.pin:
        latitude, longitude = args.pin.split(",")
        pin = {**base, "Body": "", "Latitude": latitude.strip(), "Longitude": longitude.strip()}
        forms.append((f"[pin {args.pin}]", {**pin, **({"Address": args.place} if args.place else {})}))
    return [(label, {**form, "MessageSid": f"SMsim{uuid.uuid4().hex[:28]}"}) for label, form in forms]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="sender", required=True, help="the citizen's number, e.g. +233XXXXXXXXX")
    parser.add_argument("--url", default="http://localhost:8000", help="the API (default http://localhost:8000)")
    parser.add_argument("--pin", help="a shared location as LAT,LON, sent after the messages")
    parser.add_argument("--place", help="the pin's address, as WhatsApp sends it with a named place")
    parser.add_argument("messages", nargs="*", help="messages to send in turn")
    args = parser.parse_args()
    if not (args.messages or args.pin):
        parser.error("give a message, a --pin, or both")
    env = dotenv_values(ENV)
    token, public = env.get("TWILIO_AUTH_TOKEN"), env.get("PUBLIC_API_URL")
    if not token or not public:
        print("TWILIO_AUTH_TOKEN and PUBLIC_API_URL must be set in backend/.env")
        return 1
    if env.get("WHATSAPP_PROVIDER") == "twilio":
        print("Note: WHATSAPP_PROVIDER=twilio in .env, so an API using it sends real, charged replies.")
    validator = RequestValidator(token)
    with httpx.Client(timeout=30) as client:
        for label, form in _forms(args, env.get("TWILIO_WHATSAPP_FROM", "")):
            signature = validator.compute_signature(f"{public.rstrip('/')}{PATH}", form)
            response = client.post(f"{args.url.rstrip('/')}{PATH}", data=form, headers={"X-Twilio-Signature": signature})
            print(f"> {label}  ({response.status_code})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
