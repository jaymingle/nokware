"""A WhatsApp phone in the terminal: sends Twilio-signed webhooks to the API, as Twilio would.

Each message is signed with TWILIO_AUTH_TOKEN for PUBLIC_API_URL (the address
Twilio calls), then posted to --url. Replies go wherever the API sends them:
with WHATSAPP_PROVIDER=log they only appear in the API's log; with
WHATSAPP_PROVIDER=twilio they are real WhatsApp messages, and Twilio charges
for each. Photos can't be simulated: they need a real Twilio media link.
A voice note can (--voice FILE): the file is served from this machine for the
API to fetch, as it would fetch one from Twilio. So can a pin from WhatsApp's
location button (--pin). Both are sent after any messages, the voice note first.

    backend/.venv/bin/python backend/scripts/whatsapp_simulator.py --from +233XXXXXXXXX --url http://localhost:8001 "Hello"
    backend/.venv/bin/python backend/scripts/whatsapp_simulator.py --from +233XXXXXXXXX --voice question.ogg
    backend/.venv/bin/python backend/scripts/whatsapp_simulator.py --from +233XXXXXXXXX --pin 5.567,-0.235 --place "Kaneshie Market"
"""

import argparse
import http.server
import sys
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx
from dotenv import dotenv_values
from twilio.request_validator import RequestValidator

ENV = Path(__file__).resolve().parents[1] / ".env"
PATH = "/api/channels/whatsapp"
AUDIO_TYPES = {".ogg": "audio/ogg", ".opus": "audio/ogg", ".mp3": "audio/mpeg", ".wav": "audio/wav", ".aiff": "audio/aiff",
               ".m4a": "audio/mp4", ".amr": "audio/amr"}


class _VoiceNote(http.server.BaseHTTPRequestHandler):
    """Stands in for Twilio's media link: the API fetches the file once, then deletes it."""

    data = b""
    done = threading.Event()

    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", AUDIO_TYPES.get(Path(self.path).suffix, "application/octet-stream"))
        self.end_headers()
        self.wfile.write(self.data)

    def do_DELETE(self) -> None:
        self.send_response(204)
        self.end_headers()
        self.done.set()

    def log_message(self, *args: object) -> None:
        pass


@contextmanager
def _serving(path: Path | None) -> Iterator[tuple[str | None, threading.Event]]:
    """The voice note at a local link for the API to fetch, while the messages are sent."""
    handler = type("Handler", (_VoiceNote,), {"data": path.read_bytes() if path else b"", "done": threading.Event()})
    if path is None:
        yield None, handler.done
        return
    server = http.server.HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/voice{path.suffix}", handler.done
    finally:
        server.shutdown()


def _forms(args: argparse.Namespace, to: str, voice_url: str | None) -> list[tuple[str, dict[str, str]]]:
    """Twilio's form fields for each message in turn, then the voice note, then the pin; with a label for each."""
    base = {"From": f"whatsapp:{args.sender}", "To": to, "NumMedia": "0"}
    forms = [(text, {**base, "Body": text}) for text in args.messages]
    if voice_url:
        voice = {"NumMedia": "1", "MediaUrl0": voice_url, "MediaContentType0": AUDIO_TYPES[args.voice.suffix.lower()]}
        forms.append((f"[voice note {args.voice.name}]", {**base, "Body": "", **voice}))
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
    parser.add_argument("--voice", type=Path, help=f"an audio file to send as a voice note ({', '.join(AUDIO_TYPES)})")
    parser.add_argument("messages", nargs="*", help="messages to send in turn")
    args = parser.parse_args()
    if not (args.messages or args.pin or args.voice):
        parser.error("give a message, a --voice note, a --pin, or any of them")
    if args.voice and args.voice.suffix.lower() not in AUDIO_TYPES:
        parser.error(f"--voice takes {', '.join(AUDIO_TYPES)}")
    env = dotenv_values(ENV)
    token, public = env.get("TWILIO_AUTH_TOKEN"), env.get("PUBLIC_API_URL")
    if not token or not public:
        print("TWILIO_AUTH_TOKEN and PUBLIC_API_URL must be set in backend/.env")
        return 1
    if env.get("WHATSAPP_PROVIDER") == "twilio":
        print("Note: WHATSAPP_PROVIDER=twilio in .env, so an API using it sends real, charged replies.")
    validator = RequestValidator(token)
    with httpx.Client(timeout=30) as client, _serving(args.voice) as (voice_url, done):
        for label, form in _forms(args, env.get("TWILIO_WHATSAPP_FROM", ""), voice_url):
            signature = validator.compute_signature(f"{public.rstrip('/')}{PATH}", form)
            response = client.post(f"{args.url.rstrip('/')}{PATH}", data=form, headers={"X-Twilio-Signature": signature})
            print(f"> {label}  ({response.status_code})")
            if "MediaUrl0" in form and not done.wait(60):
                print("  The API didn't fetch and delete the voice note within a minute.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
