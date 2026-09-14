"""Show the Arkesel account's SMS and main balances. Sends nothing and costs nothing.

    backend/.venv/bin/python backend/scripts/sms_balance.py
"""

import sys

from app.services.sms import SmsError, SmsNotConfigured, arkesel


def main() -> int:
    try:
        provider = arkesel()
        balances = provider.balance()
    except (SmsNotConfigured, SmsError) as error:
        print(error)
        return 1
    mode = "sandbox (nothing is delivered or charged)" if provider.sandbox else "LIVE (messages are delivered and charged)"
    print(f"Arkesel, sender ID {provider.sender!r}, {mode}")
    for key, value in balances.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
