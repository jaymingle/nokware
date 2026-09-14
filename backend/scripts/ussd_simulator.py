"""A USSD phone in the terminal: sends Arkesel-shaped callbacks to the API and prints each screen.

Interactive, or scripted with --keys. The callback address uses ARKESEL_USSD_TOKEN
from backend/.env. Messages the API sends (answers by SMS, report updates) go
through its own SMS settings: with ARKESEL_SANDBOX=true nothing is delivered or
charged.

    backend/.venv/bin/python backend/scripts/ussd_simulator.py --msisdn 233XXXXXXXXX
    backend/.venv/bin/python backend/scripts/ussd_simulator.py --msisdn 233XXXXXXXXX --keys 3 K7QM-4TXP
"""

import argparse
import sys
import textwrap
import uuid
from pathlib import Path

import httpx
from dotenv import dotenv_values

ENV = Path(__file__).resolve().parents[1] / ".env"
DIAL = "*928*1#"


def show(screen: dict[str, object]) -> None:
    edge = "+" + "-" * 34 + "+"
    print(edge)
    for line in str(screen["message"]).splitlines():
        for part in textwrap.wrap(line, 32) or [""]:  # a phone wraps long lines
            print(f"| {part:<32} |")
    print(edge, "(waiting for a key)" if screen["continueSession"] else "(session ended)")


def press(client: httpx.Client, url: str, session: dict[str, object], text: str, new: bool) -> dict[str, object]:
    body = {**session, "newSession": new, "userData": text}
    reply = client.post(url, json=body, timeout=30).raise_for_status().json()
    show(reply)
    return reply


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--msisdn", required=True, help="the dialling number, e.g. 233XXXXXXXXX")
    parser.add_argument("--url", default="http://localhost:8000", help="the API (default http://localhost:8000)")
    parser.add_argument("--keys", nargs="*", help="keypresses to send in turn, instead of typing them")
    args = parser.parse_args()
    token = dotenv_values(ENV).get("ARKESEL_USSD_TOKEN")
    if not token:
        print("ARKESEL_USSD_TOKEN is not set in backend/.env")
        return 1
    url = f"{args.url.rstrip('/')}/api/channels/ussd/{token}"
    session = {"sessionID": uuid.uuid4().hex, "userID": "SIMULATOR", "msisdn": args.msisdn, "network": "SIMULATOR"}
    with httpx.Client() as client:
        reply = press(client, url, session, DIAL, new=True)
        presses = iter(args.keys) if args.keys is not None else None
        while reply["continueSession"]:
            key = next(presses, None) if presses is not None else input("> ")
            if key is None:
                print("(no more keys: the session is left open)")
                break
            if presses is not None:
                print(f"> {key}")
            reply = press(client, url, session, key, new=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
