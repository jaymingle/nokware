"""A WhatsApp phone in the terminal: sends Twilio-signed webhooks to the API, as Twilio would.

Each message is signed with TWILIO_AUTH_TOKEN for PUBLIC_API_URL (the address
Twilio calls), then posted to --url. Replies go wherever the API sends them:
with WHATSAPP_PROVIDER=log they only appear in the API's log; with
WHATSAPP_PROVIDER=twilio they are real WhatsApp messages, and Twilio charges
for each. Photos can't be simulated: they need a real Twilio media link.

    backend/.venv/bin/python backend/scripts/whatsapp_simulator.py --from +233XXXXXXXXX --url http://localhost:8001 "Hello"
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="sender", required=True, help="the citizen's number, e.g. +233XXXXXXXXX")
    parser.add_argument("--url", default="http://localhost:8000", help="the API (default http://localhost:8000)")
    parser.add_argument("messages", nargs="+", help="messages to send in turn")
    args = parser.parse_args()
    env = dotenv_values(ENV)
    token, public = env.get("TWILIO_AUTH_TOKEN"), env.get("PUBLIC_API_URL")
    if not token or not public:
        print("TWILIO_AUTH_TOKEN and PUBLIC_API_URL must be set in backend/.env")
        return 1
    if env.get("WHATSAPP_PROVIDER") == "twilio":
        print("Note: WHATSAPP_PROVIDER=twilio in .env, so an API using it sends real, charged replies.")
    validator = RequestValidator(token)
    with httpx.Client(timeout=30) as client:
        for text in args.messages:
            form = {"From": f"whatsapp:{args.sender}", "To": env.get("TWILIO_WHATSAPP_FROM", ""), "Body": text,
                    "NumMedia": "0", "MessageSid": f"SMsim{uuid.uuid4().hex[:28]}"}
            signature = validator.compute_signature(f"{public.rstrip('/')}{PATH}", form)
            response = client.post(f"{args.url.rstrip('/')}{PATH}", data=form, headers={"X-Twilio-Signature": signature})
            print(f"> {text}  ({response.status_code})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
