"""Show the configured SMS account's balance (SMS_PROVIDER: Arkesel or BMS). Sends nothing and costs nothing.

    backend/.venv/bin/python backend/scripts/sms_balance.py
"""

import sys

from app.config import get_settings
from app.services.sms import SmsError, SmsNotConfigured, arkesel
from app.services.sms_bms import bms


def main() -> int:
    provider_name = get_settings().sms_provider
    try:
        provider = bms() if provider_name == "bms" else arkesel()
        balances = provider.balance()
    except (SmsNotConfigured, SmsError) as error:
        print(error)
        return 1
    if provider_name == "bms":
        print(f"BMS Africa, sender ID {provider.sender!r}, LIVE (there is no sandbox: every message is charged)")
    else:
        sandbox = getattr(provider, "sandbox", False)
        mode = "sandbox (nothing is delivered or charged)" if sandbox else "LIVE (messages are delivered and charged)"
        print(f"Arkesel, sender ID {provider.sender!r}, {mode}")
    for key, value in balances.items():
        print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
