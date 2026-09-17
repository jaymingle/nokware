"""Budget rows out of the Assembly's PBB documents, and only where a block proves itself.

Ghana's programme-based budget prints "Budget Details by Chart of Account": not a
drawn table but a machine-written block, repeated down the document. Each block
names one fund source and one organisation, states that fund source's total, and
then breaks it down:

    Fund Type/Source  12200  IGF  Total By Fund Source   161,050
    Organisation      1010101006  Accra Metropolitan Assembly - Accra_Administration_…
    Use of goods and services                            153,000
    Objective   410501  16.7 Ensure resp. incl. participatory rep. decision making
                                                         153,000
    Program     93001   Management and Administration
                                                         153,000
    Sub-Program 93001004  SP1.4: Planning, Coordination and Statistics   153,000
    Operation   910101  …                                  30,000

An amount repeats at every level, so summing what looks like a total double
counts — that is what makes these documents look unreadable. The rows that are
both unambiguous and useful are the **sub-programme** lines: one line, one
amount, under one programme, one department and one fund source.

So each block is read into rows, and then the block must prove itself: its rows
must add up to the fund-source total it states. A block that doesn't reconcile is
dropped whole — never partly kept, never rounded to fit. A document is published
only if nearly all of its blocks reconcile (see MIN_VERIFIED); anything else is
left out, and Ask says the figures aren't available rather than half-quoting a
budget.

This reads what the document states. It doesn't add years together, convert
anything, or infer a figure that isn't printed.
"""

import io
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass

import pdfplumber

logger = logging.getLogger(__name__)

MARKER = "BUDGET DETAILS BY CHART OF ACCOUNT"
MIN_VERIFIED = 0.95  # a document whose blocks don't nearly all reconcile isn't published at all
PENCE = 0.5  # a block reconciles when its rows land within this of the stated total
ECONOMIC = ("Compensation of employees", "Use of goods and services", "Non Financial Assets", "Social benefits",
            "Other expense", "Interest", "Subsidies", "Grants", "Consumption of fixed capital")
_YEAR = re.compile(rf"{MARKER},\s*(\d{{4}})")
_AMOUNT = re.compile(r"(-?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?)\s*$")
_FUND = re.compile(r"^Fund Type/Source\s+(\d+)\s*(.*?)\s*Total By Fund Source\s+(.+)$")
_ORGANISATION = re.compile(r"^Organisation\s+(\d+)\s+(.*)$")
_SUB_PROGRAM = re.compile(r"^Sub-Program\s+(\d+)\s+(.*?)\s+(-?[\d,]+(?:\.\d{1,2})?)$")
_PROGRAM = re.compile(r"^Program\s+(\d+)\s+(.*)$")


@dataclass(frozen=True)
class BudgetRow:
    """One sub-programme's approved amount, as the document prints it."""

    year: int
    fund_source: str  # "IGF", "GOG", "DACF": how it is paid for
    sector: str  # the organisation path's second part: Administration, Waste Management, Health…
    department: str  # the department named in the organisation path
    program: str
    sub_program: str
    economic: str  # compensation, goods and services, or assets: what kind of spending
    amount: float
    page: int


@dataclass(frozen=True)
class Extracted:
    """What a document gave up, and how much of it proved itself."""

    document_id: str
    rows: list[BudgetRow]
    blocks: int
    verified_blocks: int

    @property
    def share(self) -> float:
        return self.verified_blocks / self.blocks if self.blocks else 0.0

    @property
    def publishable(self) -> bool:
        return bool(self.blocks) and self.share >= MIN_VERIFIED


def amount(text: str) -> float | None:
    found = _AMOUNT.search(text.strip())
    try:
        return float(found.group(1).replace(",", "")) if found else None
    except ValueError:
        return None


def _departments(path: str) -> tuple[str, str]:
    """The sector and the department from an organisation path, e.g. …_Waste Management_Metro Waste…_Greater Accra."""
    parts = [part.strip() for part in path.split("_") if part.strip()]
    sector = parts[1] if len(parts) > 2 else ""
    department = parts[-2] if len(parts) > 2 else (parts[-1] if parts else "")
    return sector, department


def _blocks(lines: list[tuple[str, int]]) -> Iterator[tuple[list[str], int]]:
    """The document's blocks with the page each starts on. A block runs from one institution to the next, and
    runs on across a page break: reading page by page would cut one in half and lose the half that has the total."""
    current: list[str] = []
    page = 0
    for line, number in lines:
        if line.startswith("Institution ") and current:
            yield current, page
            current = []
        if not current:
            page = number
        current.append(line)
    if current:
        yield current, page


def _rows_in(block: list[str], year: int, page: int) -> tuple[list[BudgetRow], float | None]:
    """The sub-programme rows in one block, and the fund-source total it says they add up to."""
    total: float | None = None
    fund = sector = department = program = economic = ""
    rows: list[BudgetRow] = []
    for index, line in enumerate(block):
        if found := _FUND.match(line):
            fund, total = (found.group(2) or found.group(1)).strip(), amount(found.group(3))
        elif found := _ORGANISATION.match(line):
            path = found.group(2)
            if index + 1 < len(block) and "_" in block[index + 1] and not block[index + 1].startswith(("Location", "Objective")):
                path = f"{path} {block[index + 1].strip()}"  # an organisation path wraps onto the next line
            sector, department = _departments(path)
        elif any(line.startswith(kind) for kind in ECONOMIC) and index + 1 < len(block) and block[index + 1].startswith("Objective"):
            economic = line.rsplit(" ", 1)[0].strip() if amount(line) is not None else line.strip()
        elif found := _PROGRAM.match(line):
            program = found.group(2).strip()
        elif found := _SUB_PROGRAM.match(line):
            value = amount(found.group(3))
            if value is not None:
                rows.append(BudgetRow(year, fund, sector, department, program, found.group(2).strip(), economic, value, page))
    return rows, total


def _reconciles(rows: list[BudgetRow], total: float | None) -> bool:
    """Whether the block's rows add up to the total it states. Anything else is dropped whole."""
    return total is not None and bool(rows) and abs(sum(row.amount for row in rows) - total) <= PENCE


def _lines(data: bytes) -> tuple[list[tuple[str, int]], int | None]:
    """Every line of the budget's detail pages, with its page, and the year the pages state. Page furniture is
    dropped: the heading repeats on each page and would otherwise land inside a block that runs on."""
    lines: list[tuple[str, int]] = []
    year: int | None = None
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if MARKER not in text:
                continue
            found = _YEAR.search(text)
            year = year or (int(found.group(1)) if found else None)
            for line in text.splitlines():
                if line.strip() and not line.startswith((MARKER, "Amount (GH")):
                    lines.append((line, page.page_number))
    return lines, year


def read_pdf(data: bytes, document_id: str) -> Extracted:
    """Every block in a PBB document, with the ones that don't prove themselves left out."""
    rows: list[BudgetRow] = []
    blocks = verified = 0
    lines, year = _lines(data)
    if year is None:
        return Extracted(document_id, [], 0, 0)
    for block, page in _blocks(lines):
        found, total = _rows_in(block, year, page)
        if total is None and not found:
            continue  # not a block: the pages before the details begin
        blocks += 1
        if _reconciles(found, total):
            verified += 1
            rows.extend(found)
    return Extracted(document_id, rows, blocks, verified)
