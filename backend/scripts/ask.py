"""Ask the Ledger a question from the terminal and print the cited answer.

Runs the same pipeline as POST /api/ask, so it is a quick way to judge retrieval
quality without a frontend. It prints the answer, the search queries used, and
each labelled source document (cited or merely retrieved) with snippets of the
chunks retrieved from it.

    backend/.venv/bin/python backend/scripts/ask.py "What does the 2026 fee-fixing resolution cover?"
    backend/.venv/bin/python backend/scripts/ask.py --full "..."   # whole chunks, not snippets

Exits 0 when an answer is printed, 1 on invalid input or a settings/service error.
"""

import argparse
import sys
import textwrap
from itertools import groupby

from pydantic import ValidationError

from app.config import get_settings, settings_error_summary
from app.schemas.ask import AskRequest
from app.services.appwrite_client import quiet_sdk_deprecation_warnings
from app.services.rag import UNKNOWN_YEAR, RagAnswer, Source, answer_question

SNIPPET_LENGTH = 220
WRAP_WIDTH = 100


def format_document(label: str, chunks: list[Source], full: bool) -> str:
    first = chunks[0]
    status = "cited" if first["cited"] else "retrieved, not cited"
    lines = [
        f"[{label}] {first['title'] or '(untitled)'}  ({status})",
        f"     {first['document_id']} · {first['department']} · {first['source_type']} · "
        f"year {first['document_year'] or UNKNOWN_YEAR} · {len(chunks)} chunk(s)",
    ]
    for chunk in chunks:
        text = " ".join(chunk["chunk_text"].split())
        if not full and len(text) > SNIPPET_LENGTH:
            text = f"{text[:SNIPPET_LENGTH].rstrip()}…"
        lines.append(textwrap.fill(text, WRAP_WIDTH, initial_indent="     › ", subsequent_indent="       "))
    return "\n".join(lines)


def print_answer(question: str, result: RagAnswer, full: bool) -> None:
    sources = result["sources"]
    documents = [(label, list(chunks)) for label, chunks in groupby(sources, key=lambda s: s["label"])]
    cited = sum(chunks[0]["cited"] for _, chunks in documents)
    print(f"Q: {question}\n\n{result['answer']}\n")
    print("Searched for: " + " | ".join(result["search_queries"]))
    print(f"Sources: {len(documents)} document(s), {cited} cited, {len(sources)} chunk(s)\n")
    for label, chunks in documents:
        print(f"{format_document(label, chunks, full)}\n")


def parse_question() -> tuple[str, bool]:
    parser = argparse.ArgumentParser(description="Ask the Ledger a question.")
    parser.add_argument("question", nargs="+", help="the question (quoting is optional)")
    parser.add_argument("--full", action="store_true", help="print whole chunks instead of snippets")
    args = parser.parse_args()
    try:
        request = AskRequest(question=" ".join(args.question))  # same rules as POST /api/ask
    except ValidationError as exc:
        parser.error(exc.errors(include_url=False)[0]["msg"])
    return request.question, args.full


def main() -> int:
    question, full = parse_question()
    quiet_sdk_deprecation_warnings()
    try:
        get_settings()
    except ValidationError as exc:
        print(settings_error_summary(exc))
        return 1
    try:
        result = answer_question(question)
    except Exception as exc:  # a clean one-line error, not a traceback
        print(f"Ask failed: {type(exc).__name__}: {exc}")
        return 1
    print_answer(question, result, full)
    return 0


if __name__ == "__main__":
    sys.exit(main())
