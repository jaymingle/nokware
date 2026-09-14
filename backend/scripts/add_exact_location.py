"""Make room for a precise location a personal-safety reporter chooses to share.

- report_contacts gains exactLocation (encrypted at rest) and exactLocationAt.
  Kept with the citizen's numbers, so the existing job deletes it with them 30
  days after the case closes.
- case_history's action gains location_shared, location_viewed and
  location_removed (who shared, viewed or removed it, and when; never where).

A dry run by default: it prints what it would do. --yes applies it. It only
adds; nothing is deleted. Safe to re-run. Run it before an API with this code
takes a location.

    backend/.venv/bin/python backend/scripts/add_exact_location.py [--yes]
"""

import argparse
import sys

from app.services.appwrite_client import DATABASE_ID, get_databases, quiet_sdk_deprecation_warnings
from app.services.citizen_reports import CONTACTS_COLLECTION as CONTACTS
from create_citizen_reports import Creator, adjust_history, ensure, wait_for_attributes

LOCATION_MAX = 1000  # the stored JSON: an address of up to 400 characters and a pin


def attributes() -> dict[str, Creator]:
    db, c = get_databases(), (DATABASE_ID, CONTACTS)
    return {
        "exactLocation": lambda: db.create_string_attribute(*c, "exactLocation", LOCATION_MAX, False, encrypt=True),
        "exactLocationAt": lambda: db.create_datetime_attribute(*c, "exactLocationAt", False),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="make the changes (default: a dry run)")
    args = parser.parse_args()
    quiet_sdk_deprecation_warnings()
    if not args.yes:
        print(f"[dry run] would add {CONTACTS}.exactLocation (encrypted) and .exactLocationAt, and the location"
              " steps to case_history.action (anything that exists is left as it is)")
        return 0
    creators = attributes()
    for key, create in creators.items():
        ensure(f"attribute {CONTACTS}.{key}", create)
    wait_for_attributes(CONTACTS, list(creators))
    adjust_history()
    return 0


if __name__ == "__main__":
    sys.exit(main())
