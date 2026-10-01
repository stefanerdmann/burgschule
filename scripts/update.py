"""Discover, validate and publish the currently linked school lunch menus."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import xml.etree.ElementTree as ET

import pymupdf
from scrapling.parser import Selector

from .pdf_menu import LayoutError, parse_pdf

HOME = "https://burgschule-nieder-olm.de"
PRIMARY = HOME + "/aktuelles/"
SITEMAP = HOME + "/sitemap_index.xml"
DOMAIN = "burgschule-nieder-olm.de"
MAX_BYTES = 10 * 1024 * 1024
USER_AGENT = "Burgschule-Speiseplan/1.0 (+https://burgschule-nieder-olm.de/aktuelles/; daily public menu check)"
DATA = Path(__file__).resolve().parents[1] / "site/data/menu.json"
WARNINGS = Path(__file__).resolve().parents[1] / "import-warnings.json"
PDF_HINT = re.compile(r"speise[n]?plan|menüplan", re.IGNORECASE)
PDF_DATE = re.compile(r"\b(\d{2})\.(\d{2})\.(20\d{2})\b")
UPLOAD_DATE = re.compile(r"/uploads/(20\d{2})/(0[1-9]|1[0-2])/", re.IGNORECASE)


@dataclass(frozen=True)
class Link:
    url: str
    label: str
    page: str


def school_url(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme == "https" and parsed.hostname == DOMAIN and parsed.port is None


class SchoolRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, msg, headers, newurl):
        if not school_url(urljoin(request.full_url, newurl)):
            raise ValueError("Weiterleitung außerhalb der Schul-Domain")
        return super().redirect_request(request, file, code, msg, headers, newurl)


OPENER = build_opener(SchoolRedirect)


def fetch(url: str, size: int = MAX_BYTES) -> bytes:
    if not school_url(url):
        raise ValueError("Nur HTTPS-Adressen der Schul-Domain zulässig")
    with OPENER.open(Request(url, headers={"User-Agent": USER_AGENT}), timeout=20) as reply:
        if not school_url(reply.url):
            raise ValueError("Weiterleitung außerhalb der Schul-Domain")
        body = reply.read(size + 1)
        if len(body) > size:
            raise ValueError("Datei zu groß")
        return body


def pdf_links(html: bytes, page: str) -> list[Link]:
    selector = Selector(html, url=page)
    found = []
    for anchor in selector.css("a[href]"):
        url = urljoin(page, anchor.attrib.get("href", ""))
        if not school_url(url) or not urlsplit(url).path.lower().endswith(".pdf"):
            continue
        label = " ".join(str(anchor.text or "").split())
        # The primary menu section currently has a stray, older link labelled
        # only '–'. Include it, but never treat all site PDFs as lunch menus.
        parent = anchor.parent
        nearby = parent.get_all_text() if parent and parent.tag in ("p", "div", "li", "section") else ""
        if PDF_HINT.search(" ".join((label, url, nearby))):
            found.append(Link(url, label, page))
    return found


def sitemap_pages() -> list[str]:
    """Only the school's public pages/posts, bounded to avoid crawling the web."""
    root = ET.fromstring(fetch(SITEMAP, 2_000_000))
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    maps = [loc.text for loc in root.findall(".//s:loc", ns)
            if loc.text and re.search(r"/(page|post)-sitemap\.xml$", loc.text)]
    pages = []
    for url in maps[:2]:
        if not school_url(url):
            continue
        xml = ET.fromstring(fetch(url, 2_000_000))
        pages += [loc.text for loc in xml.findall(".//s:loc", ns)
                  if loc.text and school_url(loc.text) and loc.text != PRIMARY]
    # Page sitemap first, posts second; limited even if the site grows hugely.
    return list(dict.fromkeys(pages))[:40]


def document_max_date(payload: bytes) -> date | None:
    try:
        with pymupdf.open(stream=payload, filetype="pdf") as doc:
            if len(doc) > 30:
                raise LayoutError("Unerwartet viele PDF-Seiten")
            found = set()
            for page in doc:
                for day, month, year in PDF_DATE.findall(page.get_text()):
                    try:
                        found.add(date(int(year), int(month), int(day)))
                    except ValueError:
                        pass
            return max(found) if found else None
    except LayoutError:
        raise
    except Exception as exc:
        raise LayoutError("Kein lesbares PDF") from exc


def precedence(source: dict, other: dict) -> int:
    """Positive only when this PDF is *unambiguously* newer for an overlap."""
    if source["url"] == other["url"]:
        return 1  # same URL, content has changed
    if source["start"] > other["start"] and source["end"] >= other["end"]:
        return 1
    if source["start"] < other["start"] and source["end"] <= other["end"]:
        return -1
    a, b = UPLOAD_DATE.search(source["url"]), UPLOAD_DATE.search(other["url"])
    if a and b and a.group(0) != b.group(0):
        return 1 if a.group(0) > b.group(0) else -1
    return 0


def merge(base: dict, incoming: dict, source: dict, sources: dict, warnings: list[str],
          previously_published: set[str]) -> None:
    for day, value in incoming["days"].items():
        new = {**value, "source": source["url"]}
        old = base.get(day)
        if old is None or old["source"] == source["url"]:
            base[day] = new
        else:
            order = precedence(source, sources[old["source"]])
            if order > 0:
                base[day] = new
            elif order == 0:
                # Retain last published entry if one exists; at first import,
                # explicitly block the conflicting day instead of guessing.
                if day not in previously_published or old.get("status") == "uncertain":
                    base[day] = {"status": "uncertain", "reason": "Mehrere widersprüchliche PDFs", "source": source["url"]}
                warnings.append(f"{day}: überlappende PDFs ohne eindeutigen Vorrang")


def update(today: date, previous: dict | None = None,
           get=fetch, pages=sitemap_pages) -> tuple[dict, list[str]]:
    previous = previous or {}
    warnings: list[str] = []
    candidates: dict[str, Link] = {}
    try:
        for link in pdf_links(get(PRIMARY), PRIMARY):
            candidates[link.url] = link
    except Exception as exc:
        warnings.append(f"Aktuelles nicht erreichbar: {exc}")
    discovered: dict[str, tuple[dict, dict]] = {}

    def scan(links: list[Link]) -> None:
        for link in links:
            if link.url in discovered or link.url in attempted or len(attempted) >= 18:
                continue
            attempted.add(link.url)
            payload = None
            try:
                payload = get(link.url)
                if not payload.startswith(b"%PDF-"):
                    raise LayoutError("Datei ist kein PDF")
                latest = document_max_date(payload)
                # The page currently has an unrelated 2024 menu from another
                # provider; it must not generate errors every morning in 2026.
                if latest and latest < today - timedelta(days=21):
                    continue
                parsed = parse_pdf(payload)
                source = {"url": link.url, "page": link.page, "label": link.label,
                          "sha256": hashlib.sha256(payload).hexdigest(),
                          "start": parsed["start"], "end": parsed["end"]}
                discovered[link.url] = (source, parsed)
                for day, value in parsed["days"].items():
                    if value["status"] != "ok" and date.fromisoformat(day) >= today:
                        warnings.append(f"{day}: nicht eindeutig lesbar ({value['reason']}); {link.url}")
            except Exception as exc:
                warnings.append(f"PDF-Import fehlgeschlagen ({link.url}): {exc}")
                old_source = previous.get("sources", {}).get(link.url)
                if old_source:
                    changed = payload is not None and hashlib.sha256(payload).hexdigest() != old_source["sha256"]
                    if changed:
                        changed_urls.add(link.url)

    attempted: set[str] = set()
    changed_urls: set[str] = set()
    scan(list(candidates.values()))
    latest_end = max((date.fromisoformat(s["end"]) for s, _ in discovered.values()), default=date.min)
    if latest_end < today + timedelta(days=7):
        try:
            other: list[Link] = []
            for page in pages():
                try:
                    other.extend(pdf_links(get(page), page))
                except Exception:
                    continue
            scan(other)
        except Exception as exc:
            warnings.append(f"Fallback-Suche fehlgeschlagen: {exc}")

    # Only keep still-active plan ranges. The previous successful data survives
    # network outages, but an expired PDF is never presented as today's menu.
    sources = {url: value for url, value in previous.get("sources", {}).items()
               if date.fromisoformat(value["end"]) >= today}
    days = {key: value for key, value in previous.get("days", {}).items()
            if value.get("source") in sources}
    previously_published = set(days)
    for source, parsed in sorted(discovered.values(), key=lambda pair: (pair[0]["start"], pair[0]["end"])):
        if date.fromisoformat(source["end"]) < today:
            continue  # no long-term archive; never reinstate an expired plan
        sources[source["url"]] = source
        merge(days, parsed, source, sources, warnings, previously_published)
    for key, value in list(days.items()):
        if value["source"] in changed_urls:
            days[key] = {"status": "uncertain", "source": value["source"],
                         "reason": "Original-PDF geändert; neue Fassung nicht lesbar"}
    max_end = max((date.fromisoformat(s["end"]) for s in sources.values()), default=None)
    if max_end is None:
        warnings.append("Kein aktueller Speiseplan gefunden")
    elif max_end < today + timedelta(days=7):
        warnings.append(f"Kein Folgeplan gefunden; vorhandener Plan endet am {max_end.isoformat()}")
    fallback = previous.get("fallback_pdf")
    if candidates:
        last_link = list(candidates.values())[-1]
        fallback = {"url": last_link.url, "label": last_link.label}
    elif discovered:
        latest = max((source for source, _ in discovered.values()), key=lambda s: s["end"])
        fallback = {"url": latest["url"], "label": latest["label"]}
    data = {"schema": 1, "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "school_url": PRIMARY, "fallback_pdf": fallback,
            "sources": sources, "days": dict(sorted(days.items()))}
    return data, list(dict.fromkeys(warnings))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--today", type=date.fromisoformat,
                        help="For tests only: ISO date; production uses Europe/Berlin")
    args = parser.parse_args()
    # Actions runs in UTC. Do not infer the school's date from the runner zone.
    from zoneinfo import ZoneInfo
    today = args.today or datetime.now(ZoneInfo("Europe/Berlin")).date()
    old = json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else None
    try:
        data, warnings = update(today, old)
        DATA.parent.mkdir(parents=True, exist_ok=True)
        DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        warnings = [f"Unerwarteter Fehler im Import: {type(exc).__name__}: {exc}"]
    WARNINGS.write_text(json.dumps({"warnings": warnings}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for warning in warnings:
        print("WARNUNG:", warning)
    # A handled import error is reported through a GitHub Issue, not by losing
    # the last successful Netlify build. Fatal errors are also returned as such.
    return 0 if not any(w.startswith("Unerwarteter Fehler") for w in warnings) else 1


if __name__ == "__main__":
    raise SystemExit(main())
