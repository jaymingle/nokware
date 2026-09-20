"""An Ask answer as a PDF, saying on every page that it is not an official AMA document.

Public Sans has no cedi sign (₵) or Ghanaian letters (ɛ, ɔ), so those characters are set in Noto Sans.
"""

import io
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Image, KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.schemas.ask import AskChart, AskFigure
from app.services import export_chart
from app.services.ask_export import (
    FOOTER_NOTICE,
    HEADER_NOTICE,
    Block,
    Content,
    chart_footnote,
    figure_footnote,
    figures_heading,
    figures_notes,
)

FONTS = Path(__file__).resolve().parents[1] / "fonts"
INK, INK_SOFT, TEAL, HAIRLINE = colors.HexColor("#17242B"), colors.HexColor("#4A5A5F"), colors.HexColor("#1F6F5C"), colors.HexColor("#D6DAD4")
MARGIN = 20 * mm
TEXT_WIDTH = A4[0] - 2 * MARGIN


@lru_cache
def _fonts() -> None:
    for name in ("PublicSans-Regular", "PublicSans-SemiBold", "PublicSans-Italic", "Fraunces-Medium", "NotoSans-Regular", "NotoSans-SemiBold"):
        pdfmetrics.registerFont(TTFont(name, str(FONTS / f"{name}.ttf")))
    pdfmetrics.registerFontFamily("PublicSans", normal="PublicSans-Regular", bold="PublicSans-SemiBold",
                                  italic="PublicSans-Italic", boldItalic="PublicSans-SemiBold")


@lru_cache
def _covered() -> frozenset[int]:
    return frozenset(TTFont("PublicSans-Regular", str(FONTS / "PublicSans-Regular.ttf")).face.charToGlyph)


def markup(text: str) -> str:
    out, run = [], []
    for char in text:
        if ord(char) in _covered() or char.isspace():
            if run:
                out.append(f'<font name="NotoSans-Regular">{escape("".join(run))}</font>')
                run = []
            out.append(escape(char))
        else:
            run.append(char)
    if run:
        out.append(f'<font name="NotoSans-Regular">{escape("".join(run))}</font>')
    return "".join(out)


def _style(name: str, **overrides: object) -> ParagraphStyle:
    base = {"fontName": "PublicSans-Regular", "fontSize": 10.5, "leading": 15, "textColor": INK, "alignment": TA_LEFT}
    return ParagraphStyle(name, **{**base, **overrides})


BODY = _style("body", spaceAfter=6)
SMALL = _style("small", fontSize=8.5, leading=11.5, textColor=INK_SOFT)
LABEL = _style("label", fontName="PublicSans-SemiBold", fontSize=8, leading=11, textColor=INK_SOFT, spaceAfter=2)
QUESTION = _style("question", fontName="Fraunces-Medium", fontSize=17, leading=22, spaceAfter=4)
HEADING = _style("heading", fontName="Fraunces-Medium", fontSize=13, leading=17, spaceBefore=12, spaceAfter=6)
SOURCE = _style("source", fontName="PublicSans-SemiBold", spaceAfter=1)


def _runs(block: Block) -> str:
    return "".join(f"<b>{markup(text)}</b>" if bold else markup(text) for text, bold in block.runs)


def _answer(content: Content) -> list[object]:
    flow: list[object] = []
    items: list[ListItem] = []
    kind: str | None = None

    def close() -> None:
        nonlocal items, kind
        if items:
            bullet = kind == "bullet"
            flow.append(ListFlowable(items, bulletType="bullet" if bullet else "1", start="•" if bullet else None, leftIndent=14,
                                     bulletFontName="PublicSans-Regular", bulletFontSize=10))
        items, kind = [], None

    for block in content.blocks:
        if block.kind in ("bullet", "numbered"):
            if kind != block.kind:
                close()
            kind = block.kind
            items.append(ListItem(Paragraph(_runs(block), BODY), leftIndent=14))
            continue
        close()
        flow.append(Paragraph(_runs(block), HEADING if block.kind == "heading" else BODY))
    close()
    return flow


def _chart(chart: AskChart | None, note: str | None) -> list[object]:
    if chart is None:
        return [Paragraph(markup(note), _style("note", fontName="PublicSans-Italic", textColor=INK_SOFT))] if note else []
    image = export_chart.png(chart)
    picture = Image(io.BytesIO(image), width=TEXT_WIDTH, height=TEXT_WIDTH * _ratio(image))
    parts: list[object] = [Paragraph(markup(chart.title), HEADING)]
    if chart.note:
        parts.append(Paragraph(markup(chart.note), _style("chart-note", fontName="PublicSans-Italic", textColor=INK_SOFT, spaceAfter=4)))
    parts.append(picture)
    parts.append(Paragraph(markup(chart_footnote(chart)), SMALL))
    return [KeepTogether(parts)]


def _ratio(png: bytes) -> float:
    with PILImage.open(io.BytesIO(png)) as image:
        return image.height / image.width


def _figure(number: int, figure: AskFigure) -> list[object]:
    parts: list[object] = [Paragraph(f"<b>[F{number}]</b> {markup(figure.description)}: <b>{markup(figure.value)}</b>", BODY)]
    if figure.rows:
        table = Table([[markup(r.name), markup(r.value)] for r in figure.rows], colWidths=[TEXT_WIDTH * 0.6, TEXT_WIDTH * 0.2], hAlign="LEFT")
        table.setStyle(TableStyle([("FONT", (0, 0), (-1, -1), "PublicSans-Regular", 9.5), ("TEXTCOLOR", (0, 0), (-1, -1), INK),
                                   ("LINEBELOW", (0, 0), (-1, -1), 0.4, HAIRLINE), ("ALIGN", (1, 0), (1, -1), "RIGHT")]))
        parts.append(table)
    parts.append(Paragraph(markup(figure_footnote(figure)), SMALL))
    return [*parts, Spacer(1, 4)]


def _link(url: str) -> str:
    if not url.startswith(("https://", "http://")):
        return markup(url)
    return f'<a href="{escape(url, {chr(34): "&quot;"})}" color="#1F6F5C">{markup(url)}</a>'


def _headed(title: str, groups: list[list[object]]) -> list[object]:
    if not groups:
        return []
    return [KeepTogether([Paragraph(title, HEADING), *groups[0]]), *(item for group in groups[1:] for item in group)]


def _sources(content: Content) -> list[object]:
    groups: list[list[object]] = []
    for number, source, provenance in content.sources:
        facts = " · ".join(str(p) for p in (source.department_name, source.document_year) if p)
        lines = [Paragraph(f"[{number}] {markup(source.title)}", SOURCE)]
        lines += [Paragraph(markup(line), SMALL) for line in (facts, provenance) if line]
        if source.source_url:
            lines.append(Paragraph(f"Original: {_link(source.source_url)}", SMALL))
        if source.ledger_url:
            lines.append(Paragraph(f"Nokware's copy: {_link(source.ledger_url)}", SMALL))
        groups.append([*lines, Spacer(1, 6)])
    return _headed("Sources", groups)


def _story(content: Content) -> list[object]:
    story: list[object] = [Paragraph("YOUR QUESTION", LABEL), Paragraph(markup(content.question), QUESTION),
                           Paragraph(markup(f"Answered {content.answered}"), SMALL), Spacer(1, 10), Paragraph("Answer", HEADING)]
    story += _answer(content)
    if content.no_information:
        story.append(Paragraph(markup(content.no_information), BODY))
    story += _chart(content.chart, content.chart_note)
    if content.figures:
        story += _headed(figures_heading(content.figures), [[KeepTogether(_figure(n, f))] for n, f in content.figures])
        story += [Paragraph(markup(note), SMALL) for note in figures_notes(content.figures)]
    return story + _sources(content)


class _Pages(Canvas):
    """Defers each page's header and footer until the page count is known, for "Page 2 of 3"."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self._pages: list[dict[str, object]] = []

    def showPage(self) -> None:
        self._pages.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        for page in self._pages:
            self.__dict__.update(page)
            _frame(self, len(self._pages))
            super().showPage()
        super().save()


def _frame(canvas: Canvas, total: int) -> None:
    width, height = A4
    canvas.saveState()
    canvas.setFillColor(INK)
    canvas.roundRect(MARGIN, height - 16 * mm, 8 * mm, 8 * mm, 1.6 * mm, stroke=0, fill=1)
    canvas.setFillColor(colors.white)
    canvas.setFont("Fraunces-Medium", 14)
    canvas.drawCentredString(MARGIN + 4 * mm, height - 13.9 * mm, "N")
    canvas.setFillColor(INK)
    canvas.setFont("Fraunces-Medium", 13)
    canvas.drawString(MARGIN + 10.5 * mm, height - 11.6 * mm, "Nokware")
    canvas.setFont("PublicSans-Regular", 8)
    canvas.setFillColor(INK_SOFT)
    canvas.drawString(MARGIN + 10.5 * mm, height - 15.4 * mm, "Accra's public record")
    notice = Paragraph(markup(HEADER_NOTICE), _style("notice", fontSize=8, leading=10.5, textColor=INK_SOFT))
    notice.wrapOn(canvas, 95 * mm, 20 * mm)
    notice.drawOn(canvas, width - MARGIN - 95 * mm, height - 16.4 * mm)
    canvas.setStrokeColor(HAIRLINE)
    canvas.line(MARGIN, height - 19 * mm, width - MARGIN, height - 19 * mm)
    canvas.line(MARGIN, 15 * mm, width - MARGIN, 15 * mm)
    canvas.setFont("PublicSans-Regular", 7.5)
    canvas.drawString(MARGIN, 11 * mm, FOOTER_NOTICE)
    canvas.drawRightString(width - MARGIN, 11 * mm, f"Page {canvas.getPageNumber()} of {total}")
    canvas.restoreState()


def pdf(content: Content) -> bytes:
    _fonts()
    out = io.BytesIO()
    document = SimpleDocTemplate(
        out, pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN, topMargin=26 * mm, bottomMargin=22 * mm,
        title=f"Nokware answer: {content.question[:120]}", author="Nokware (not an official AMA document)",
        subject=HEADER_NOTICE, creator="Nokware",
    )
    document.build(_story(content), canvasmaker=_Pages)
    return out.getvalue()
