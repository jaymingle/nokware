"""What each language still needs, with the English beside it, for the person who will write or check it.

    .venv/bin/python scripts/phrases_to_review.py          every language
    .venv/bin/python scripts/phrases_to_review.py tw       one language

Text marked CRITICAL is what someone may act on while in danger. It shows in
English until a named person has checked the translation: add "reviewed_by" and
"reviewed_on" to that key in app/data/phrases/<language>.json, and it ships.
"""

import sys

from app.services.phrases import NAMES, Language, missing


def report(language: Language) -> None:
    gaps = missing(language)
    print(f"\n{NAMES[language]} ({language.value}): {len(gaps)} to go\n" + "=" * 60)
    for gap in sorted(gaps, key=lambda m: (not m.critical, m.key)):
        mark = "CRITICAL — shows in English until reviewed" if gap.critical else gap.reason
        print(f"\n{gap.key}  [{mark}]\n  English: {gap.english}")
    if not gaps:
        print("\nNothing outstanding.")


def main() -> None:
    wanted = sys.argv[1:] or [language.value for language in Language if language is not Language.ENGLISH]
    for value in wanted:
        report(Language(value))
    print()


if __name__ == "__main__":
    main()
