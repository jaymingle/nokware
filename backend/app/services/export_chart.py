"""An Ask chart as a PNG for the PDF and Word exports, drawn with Pillow in the site's colours.

ask_charts decided the kind, the values and the axis; this only draws them. An
exact count is a bar from zero, or a point on a line. "Fewer than 5" is never a
value: on a bar it is a hatched block from 1 to 4 with a dashed edge, on a line
a dashed span from 1 to 4 where the line breaks. Pies and donuts are only ever
asked to draw exact counts. Drawn at twice the size it is shown, so print is sharp.
"""

import io
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.schemas.ask import AskChart, ChartValue

FONTS = Path(__file__).resolve().parents[1] / "fonts"
WIDTH = 1400
INK, INK_SOFT, HAIRLINE, PAPER = (23, 36, 43), (74, 90, 95), (214, 218, 212), (255, 255, 255)
PALETTE = [(31, 111, 92), (169, 118, 31), (140, 50, 48), (74, 90, 95), (120, 168, 150), (212, 178, 110), (190, 120, 116)]
LABEL, TICK = 26, 24
PAD_L, PAD_R, PAD_T = 96, 40, 28
Box = tuple[float, float, float, float]


@lru_cache
def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / ("PublicSans-SemiBold.ttf" if bold else "PublicSans-Regular.ttf")), size)


def colour(index: int) -> tuple[int, int, int]:
    return PALETTE[index % len(PALETTE)]


def short(value: ChartValue) -> str:
    return "<5" if value.low != value.high else value.shown


def _text_width(text: str, size: int = LABEL) -> float:
    return font(size).getlength(text)


def _dashed(draw: ImageDraw.ImageDraw, start: tuple[float, float], end: tuple[float, float], fill: tuple[int, int, int], width: int = 3) -> None:
    length = math.dist(start, end)
    steps = max(1, int(length // 12))
    for i in range(0, steps, 2):
        a, b = i / steps, min(1, (i + 1) / steps)
        draw.line([(start[0] + (end[0] - start[0]) * a, start[1] + (end[1] - start[1]) * a),
                   (start[0] + (end[0] - start[0]) * b, start[1] + (end[1] - start[1]) * b)], fill=fill, width=width)


def _hatched(image: Image.Image, box: Box, fill: tuple[int, int, int]) -> None:
    """A range, not a value: diagonal hatching inside the box, with a dashed edge."""
    x0, y0, x1, y1 = (round(v) for v in box)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return
    tile = Image.new("RGBA", (x1 - x0, y1 - y0), (0, 0, 0, 0))
    ink = ImageDraw.Draw(tile)
    for d in range(-(y1 - y0), x1 - x0, 12):
        ink.line([(d, y1 - y0), (d + (y1 - y0), 0)], fill=(*fill, 170), width=2)
    image.paste(tile, (x0, y0), tile)
    draw = ImageDraw.Draw(image)
    for edge in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        _dashed(draw, *edge, fill=fill, width=2)


@dataclass(frozen=True)
class _Axis:
    """The value axis: where a count sits, along the chart's length."""

    start: float  # the pixel for zero
    end: float  # the pixel for axis_max
    top: int

    def at(self, value: float) -> float:
        return self.start + (self.end - self.start) * value / max(1, self.top)


def _legend(draw: ImageDraw.ImageDraw, chart: AskChart, y: float) -> float:
    """One swatch per series, in a row; how tall it was."""
    if len(chart.series) < 2:
        return 0
    x = PAD_L
    for index, series in enumerate(chart.series):
        draw.rectangle([x, y + 6, x + 24, y + 30], fill=colour(index))
        draw.text((x + 34, y), series.name, font=font(LABEL), fill=INK)
        x += 34 + _text_width(series.name) + 40
    return 48


def _wrapped(text: str, width: float) -> list[str]:
    words, lines = text.split(), [""]
    for word in words:
        trial = f"{lines[-1]} {word}".strip()
        if _text_width(trial, TICK) <= width or not lines[-1]:
            lines[-1] = trial
        else:
            lines.append(word)
    return lines[:2]


def _bar(image: Image.Image, box: Box, value: ChartValue, fill: tuple[int, int, int]) -> None:
    """An exact bar filled; a "fewer than 5" one hatched over its range (box spans low to high)."""
    if value.low == value.high:
        ImageDraw.Draw(image).rectangle(box, fill=fill)
    else:
        _hatched(image, box, fill)


def _upright_bars(image: Image.Image, chart: AskChart, top: float) -> None:
    draw = ImageDraw.Draw(image)
    bottom = image.height - 110
    axis = _Axis(bottom, top, chart.axis_max)
    _value_grid(draw, chart, axis, vertical=True)
    step = (WIDTH - PAD_L - PAD_R) / len(chart.categories)
    stacked = chart.kind == "stacked_bar"
    width = min(90, step * (0.6 if stacked or len(chart.series) == 1 else 0.8) / (1 if stacked else len(chart.series)))
    for i, name in enumerate(chart.categories):
        centre, base = PAD_L + step * (i + 0.5), 0.0
        for s, series in enumerate(chart.series):
            value = series.values[i]
            x0 = centre - width / 2 if stacked else centre - width * len(chart.series) / 2 + width * s
            low, high = (base, base + value.high) if stacked else (0 if value.low == value.high else value.low, value.high)
            if high > low:
                _bar(image, (x0, axis.at(high), x0 + width - 4, axis.at(low)), value, colour(s))
            if stacked and axis.at(low) - axis.at(high) > 34:
                draw.text((x0 + width / 2 - 2, (axis.at(low) + axis.at(high)) / 2), short(value), font=font(TICK), fill=PAPER, anchor="mm")
            elif not stacked:
                draw.text((x0 + width / 2 - 2, axis.at(high) - 8), short(value), font=font(TICK), fill=INK_SOFT, anchor="md")
            base = high if stacked else base
        for line_no, line in enumerate(_wrapped(name, step - 8)):
            draw.text((centre, bottom + 14 + line_no * 30), line, font=font(TICK), fill=INK_SOFT, anchor="ma")


def _flat_bars(image: Image.Image, chart: AskChart, top: float, label_width: float, row: float) -> None:
    draw = ImageDraw.Draw(image)
    axis = _Axis(PAD_L + label_width, WIDTH - PAD_R - 60, chart.axis_max)
    stacked = chart.kind == "stacked_bar"
    thickness = row * (0.6 if stacked or len(chart.series) == 1 else 0.8) / (1 if stacked else len(chart.series))
    _value_grid(draw, chart, axis, vertical=False, across=(top, top + row * len(chart.categories)))
    for i, name in enumerate(chart.categories):
        centre, base = top + row * (i + 0.5), 0.0
        draw.text((axis.start - 16, centre), name, font=font(LABEL), fill=INK, anchor="rm")
        for s, series in enumerate(chart.series):
            value = series.values[i]
            y0 = centre - thickness / 2 if stacked else centre - thickness * len(chart.series) / 2 + thickness * s
            low, high = (base, base + value.high) if stacked else (0 if value.low == value.high else value.low, value.high)
            if high > low:
                _bar(image, (axis.at(low), y0, axis.at(high), y0 + thickness - 4), value, colour(s))
            if stacked and axis.at(high) - axis.at(low) > 44:
                draw.text(((axis.at(low) + axis.at(high)) / 2, y0 + thickness / 2 - 2), short(value), font=font(TICK), fill=PAPER, anchor="mm")
            elif not stacked:
                draw.text((axis.at(high) + 10, y0 + thickness / 2 - 2), short(value), font=font(TICK), fill=INK_SOFT, anchor="lm")
            base = high if stacked else base


def _value_grid(draw: ImageDraw.ImageDraw, chart: AskChart, axis: _Axis, vertical: bool, across: tuple[float, float] = (0, 0)) -> None:
    """Hairlines at each tick, with its number."""
    for tick in chart.ticks:
        at = axis.at(tick)
        if vertical:
            draw.line([(PAD_L, at), (WIDTH - PAD_R, at)], fill=HAIRLINE, width=1)
            draw.text((PAD_L - 14, at), f"{tick:,}", font=font(TICK), fill=INK_SOFT, anchor="rm")
        else:
            draw.line([(at, across[0]), (at, across[1])], fill=HAIRLINE, width=1)
            draw.text((at, across[1] + 12), f"{tick:,}", font=font(TICK), fill=INK_SOFT, anchor="ma")


def _line(image: Image.Image, chart: AskChart, top: float) -> None:
    """Each series a line through its exact counts; it breaks at a "fewer than 5" month, drawn as a dashed span."""
    draw = ImageDraw.Draw(image)
    bottom = image.height - 110
    axis = _Axis(bottom, top, chart.axis_max)
    _value_grid(draw, chart, axis, vertical=True)
    step = (WIDTH - PAD_L - PAD_R) / len(chart.categories)
    x = [PAD_L + step * (i + 0.5) for i in range(len(chart.categories))]
    for s, series in enumerate(chart.series):
        points, run = [], []
        for i, value in enumerate([*series.values, None]):
            if value is not None and value.low == value.high:
                run.append((x[i], axis.at(value.high)))
                continue
            if len(run) > 1:
                draw.line(run, fill=colour(s), width=4, joint="curve")
            points, run = points + run, []
            if value is not None:
                _dashed(draw, (x[i], axis.at(value.low)), (x[i], axis.at(value.high)), colour(s), width=4)
                draw.text((x[i] + 10, axis.at(value.high)), "<5", font=font(TICK), fill=INK_SOFT, anchor="lm")
        for px, py in points:
            draw.ellipse([px - 6, py - 6, px + 6, py + 6], fill=PAPER, outline=colour(s), width=3)
    every = max(1, math.ceil(len(x) / 12))
    for i, name in enumerate(chart.categories):
        if i % every == 0 or i == len(x) - 1:
            draw.text((x[i], bottom + 14), name, font=font(TICK), fill=INK_SOFT, anchor="ma")


def _pie(image: Image.Image, chart: AskChart, top: float) -> None:
    """Slices of exact counts only (ask_charts never sends a pie a range), each named with its count and share."""
    draw = ImageDraw.Draw(image)
    values = [v.high for v in chart.series[0].values]
    total = sum(values) or 1
    size = 520
    box = (PAD_L, top + 10, PAD_L + size, top + 10 + size)
    angle = -90.0
    for i, value in enumerate(values):
        sweep = 360 * value / total
        if sweep > 0:
            draw.pieslice(box, angle, angle + sweep, fill=colour(i), outline=PAPER, width=3)
        angle += sweep
    if chart.kind == "donut":
        inset = size * 0.28
        draw.ellipse((box[0] + inset, box[1] + inset, box[2] - inset, box[3] - inset), fill=PAPER)
    for i, (name, value) in enumerate(zip(chart.categories, chart.series[0].values)):
        y = top + 20 + i * 44
        draw.rectangle([PAD_L + size + 60, y + 6, PAD_L + size + 84, y + 30], fill=colour(i))
        share = f"{round(100 * value.high / total)}%"
        draw.text((PAD_L + size + 96, y), f"{name}: {value.shown} ({share})", font=font(LABEL), fill=INK)


def png(chart: AskChart) -> bytes:
    """The chart as a PNG, WIDTH pixels wide."""
    legend = 48 if len(chart.series) > 1 else 0
    if chart.kind in ("pie", "donut"):
        height = PAD_T + max(560, 44 * len(chart.categories) + 40)
    elif chart.horizontal:
        row = 64 if len(chart.series) == 1 or chart.kind == "stacked_bar" else 40 * len(chart.series) + 24
        height = PAD_T + legend + row * len(chart.categories) + 60
    else:
        height = 760
    image = Image.new("RGB", (WIDTH, int(height)), PAPER)
    top = PAD_T + _legend(ImageDraw.Draw(image), chart, PAD_T)
    if chart.kind in ("pie", "donut"):
        _pie(image, chart, top)
    elif chart.kind == "line":
        _line(image, chart, top + 20)
    elif chart.horizontal:
        label_width = min(460, max(_text_width(c) for c in chart.categories) + 24)
        _flat_bars(image, chart, top, label_width, row)
    else:
        _upright_bars(image, chart, top + 30)
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=True)
    return out.getvalue()
