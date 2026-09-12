"""Ask the Ledger a question from the terminal and print the cited answer.

Runs the same RAG chain as POST /api/ask, so it is a quick way to judge
retrieval quality without a frontend: each source shows its rank, title,
document id, department and year, and a snippet of the retrieved chunk.

    backend/.venv/bin/python backend/scripts/ask.py "What does the 2026 fee-fixing resolution cover?"
    backend/.venv/bin/python backend/scripts/ask.py --full "..."   # whole chunks, not snippets

Exits 0 when an answer is printed, 1 on invalid input or a settings/service error.
"""

import argparse
import logging
import sys
import textwrap

from pydantic import ValidationError

from app.config import get_settings, settings_error_summary
from app.schemas.ask import AskRequest
from app.services.appwrite_client import quiet_sdk_deprecation_warnings
from app.services.rag import UNKNOWN_YEAR, RagAnswer, Source, answer_question

SNIPPET_LENGTH = 220
WRAP_WIDTH = 100


def format_source(rank: int, source: Source, full: bool) -> str:
    text = " ".join(source["chunk_text"].split())
    if not full and len(text) > SNIPPET_LENGTH:
        text = f"{text[:SNIPPET_LENGTH].rstrip()}…"
    year = source["document_year"] or UNKNOWN_YEAR
    return "\n".join(
        [
            f"[{rank}] {source['title'] or '(untitled)'}",
            f"    {source['document_id']} · {source['department']} · {source['source_type']} · year {year}",
            textwrap.indent(textwrap.fill(text, WRAP_WIDTH - 4), "    "),
        ]
    )


def print_answer(question: str, result: RagAnswer, full: bool) -> None:
    sources = result["sources"]
    documents = len({source["document_id"] for source in sources})
    print(f"Q: {question}\n\n{result['answer']}\n")
    print(f"Sources: {len(sources)} chunk(s) from {documents} document(s)\n")
    for rank, source in enumerate(sources, 1):
        print(f"{format_source(rank, source, full)}\n")


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
    logging.getLogger("google_genai.models").setLevel(logging.ERROR)  # drops an AFC usage notice
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
