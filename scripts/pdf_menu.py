"""Coordinate-based parser for the school's *known* five-column PDF layout.

Deliberately fail closed on unfamiliar layouts. PyMuPDF text order is not table order
(in this PDF it even interleaves whole columns), so plain get_text() is unsafe.
"""
from __future__ import annotations

from datetime import date, timedelta
import re

import pymupdf

DATE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
SEE_MENU_I = re.compile(r"^siehe\s*menü\s*i$", re.IGNORECASE)
ANIMAL_DISH = re.compile(r"\((?:F|G|R|K)\)|\b(?:Fisch\w*|Pute\w*|Hühn\w*|Rind\w*|Schwein\w*|Lachs\w*|Seelachs\w*|Kabeljau\w*|Pangasius\w*)\b")


class LayoutError(ValueError):
    """The PDF cannot be safely interpreted as the supported menu layout."""


def clean_text(lines: list[str]) -> str:
    # Only a hyphen at the END of a line is a typesetting break; do not alter
    # in-line phrases such as 'Roggen- und Dinkelbrot'.
    result = ""
    for line in lines:
        if result.endswith("-") and line and line[0].isalpha():
            result += line
        else:
            result += (" " if result else "") + line
    return re.sub(r"\s+", " ", result).strip()


def _balanced(text: str) -> bool:
    level = 0
    for char in text:
        if char == "(":
            level += 1
        elif char == ")":
            level -= 1
            if level < 0:
                return False
    return level == 0


def _reasonable_successor(first: str, second: str) -> bool:
    previous, following = date.fromisoformat(first), date.fromisoformat(second)
    gap = (following - previous).days
    if previous.weekday() == 4:
        # Missing whole weeks can represent holidays, not a broken PDF.
        return 3 <= gap <= 94 and gap % 7 == 3
    return gap == 1


def _page_lines(page: pymupdf.Page) -> list[tuple[float, float, float, str]]:
    """Lines in displayed (rotated) page coordinates: x0, y0, x1, text."""
    result = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            text = "".join(span["text"] for span in line["spans"]).strip()
            if text:
                rect = pymupdf.Rect(line["bbox"]) * page.rotation_matrix
                result.append((rect.x0, rect.y0, rect.x1, text))
    return result


def parse_pdf(payload: bytes) -> dict:
    """Return {days: {ISO date: {status, menu_i, menu_ii, dessert, ...}}, ...}.

    A questionable cell blocks its *whole day*, not the other four days on the page.
    Unrecognised page geometry blocks the entire document.
    """
    try:
        document = pymupdf.open(stream=payload, filetype="pdf")
    except Exception as exc:
        raise LayoutError("Kein lesbares PDF") from exc
    try:
        if not 1 <= len(document) <= 30:
            raise LayoutError("Unerwartete Seitenzahl")
        days: dict[str, dict] = {}
        for page in document:
            if page.rect.width < 650 or page.rect.height < 300:
                raise LayoutError(f"Seite {page.number + 1}: unbekanntes Seitenformat")
            lines = _page_lines(page)
            try:
                headers = sorted(
                    ((x, date.fromisoformat(f"{s[6:]}-{s[3:5]}-{s[:2]}"))
                     for x, y, _, s in lines if y < 70 and DATE.fullmatch(s)),
                    key=lambda item: item[0],
                )
            except ValueError as exc:
                raise LayoutError(f"Seite {page.number + 1}: ungültiges Datum") from exc
            if len(headers) != 5 or len({day for _, day in headers}) != 5:
                raise LayoutError(f"Seite {page.number + 1}: keine fünf eindeutigen Tages-Spalten")
            if any(day.weekday() != i for i, (_, day) in enumerate(headers)):
                raise LayoutError(f"Seite {page.number + 1}: Datum und Wochentag widersprüchlich")
            if any(headers[i + 1][1] != headers[i][1] + timedelta(days=1) for i in range(4)):
                raise LayoutError(f"Seite {page.number + 1}: Tage nicht fortlaufend")
            xs = [x for x, _ in headers]
            if not all(100 < xs[i + 1] - xs[i] < 190 for i in range(4)):
                raise LayoutError(f"Seite {page.number + 1}: Spaltengeometrie geändert")
            labels = {}
            for x, y, _, s in lines:
                if x < 50:
                    if s.strip() in ("Menü I", "Menü II", "Dessert"):
                        if s.strip() in labels:
                            raise LayoutError(f"Seite {page.number + 1}: doppelte Zeilenbeschriftung")
                        labels[s.strip()] = y
            if set(labels) != {"Menü I", "Menü II", "Dessert"} or not (
                65 <= labels["Menü I"] < labels["Menü II"] - 55
                < labels["Dessert"] - 60 < 220
            ):
                raise LayoutError(f"Seite {page.number + 1}: Menü-Zeilen nicht erkannt")
            row_bounds = {
                "menu_i": (labels["Menü I"] + 1, labels["Menü II"] - 4),
                "menu_ii": (labels["Menü II"] + 2, labels["Dessert"] - 4),
                "dessert": (labels["Dessert"] + 1, min(labels["Dessert"] + 95, 350)),
            }
            # Date starts are ~25pt to the right of each cell's left edge. A
            # line's START, not its midpoint, determines the cell when it wraps.
            for index, (start, day) in enumerate(headers):
                key = day.isoformat()
                if key in days:
                    raise LayoutError(f"Doppeltes Datum: {key}")
                left = start - 36
                right = xs[index + 1] - 36 if index < 4 else page.rect.width - 3
                cell = {}
                assigned: set[tuple[float, float, float, str]] = set()
                for name, (top, bottom) in row_bounds.items():
                    fragments = sorted(
                        (line for line in lines if left <= line[0] < right and top <= line[1] < bottom),
                        key=lambda part: (round(part[1], 1), part[0]),
                    )
                    assigned.update(fragments)
                    cell[name] = clean_text([part[3] for part in fragments])
                # Never silently omit a leading line just because its baseline
                # moved slightly: mark the day uncertain instead.
                unassigned = [line for line in lines if left <= line[0] < right
                              and labels["Menü I"] + 1 <= line[1] < row_bounds["dessert"][1]
                              and line not in assigned]
                reasons = ["Text außerhalb erkannter Menü-Zeilen"] if unassigned else []
                if any(part[2] > right + 3 for part in assigned):
                    reasons.append("Text ragt über die Tages-Spalte hinaus")
                reasons += [f"{name} fehlt" for name in row_bounds if not cell[name]]
                reasons += [f"{name}: Klammerung unvollständig"
                            for name in row_bounds if cell[name] and not _balanced(cell[name])]
                if SEE_MENU_I.fullmatch(cell["menu_ii"]):
                    # A "same as menu I" reference must not silently label a
                    # fish/meat dish as the vegetarian menu.
                    if ANIMAL_DISH.search(cell["menu_i"]):
                        reasons.append("Vegetarisches Menü verweist auf Fleisch/Fisch")
                    cell["menu_ii"] = cell["menu_i"]
                    cell["menu_ii_from_i"] = True
                else:
                    cell["menu_ii_from_i"] = False
                if reasons:
                    days[key] = {"status": "uncertain", "reason": "; ".join(reasons)}
                else:
                    days[key] = {"status": "ok", **cell}
        ordered = sorted(days)
        if len(ordered) != len(document) * 5 or any(
            not _reasonable_successor(a, b) for a, b in zip(ordered, ordered[1:])
        ):
            raise LayoutError("Datumsfolge über die Wochen hinweg unerwartet")
        return {"start": ordered[0], "end": ordered[-1], "days": days, "pages": len(document)}
    finally:
        document.close()
