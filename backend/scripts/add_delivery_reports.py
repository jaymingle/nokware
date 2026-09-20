"""Give the notifications outbox what delivery reports need.

- deliveryStatus: the provider's word for what happened (DELIVERED, FAILED, ...).
- deliveredAt: when the report said DELIVERED.
- An index on providerMessageId, so a report finds its outbox row.

A dry run by default: it prints what it would do. --yes applies it. It only
adds; nothing is deleted. Safe to re-run.

    backend/.venv/bin/python backend/scripts/add_delivery_reports.py [--yes]
"""

import argparse
import sys

from create_citizen_reports import KEY, Creator, ensure, ensure_indexes, wait_for_attributes

from app.services.appwrite_client import DATABASE_ID, get_databases, quiet_sdk_deprecation_warnings
from app.services.citizen_reports import NOTIFICATIONS_COLLECTION as OUTBOX

DELIVERY_STATUS = 32
INDEXES = {"idx_providerMessageId": (KEY, ["providerMessageId"])}


def attributes() -> dict[str, Creator]:
    db, c = get_databases(), (DATABASE_ID, OUTBOX)
    return {
        "deliveryStatus": lambda: db.create_string_attribute(*c, "deliveryStatus", DELIVERY_STATUS, False),
        "deliveredAt": lambda: db.create_datetime_attribute(*c, "deliveredAt", False),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="make the changes (default: a dry run)")
    args = parser.parse_args()
    quiet_sdk_deprecation_warnings()
    if not args.yes:
        print(f"[dry run] would add {OUTBOX}.deliveryStatus and .deliveredAt, and index {OUTBOX}.providerMessageId"
              " (any that exist are left as they are)")
        return 0
    creators = attributes()
    for key, create in creators.items():
        ensure(f"attribute {OUTBOX}.{key}", create)
    wait_for_attributes(OUTBOX, list(creators))
    ensure_indexes(OUTBOX, INDEXES)
    return 0


if __name__ == "__main__":
    sys.exit(main())
