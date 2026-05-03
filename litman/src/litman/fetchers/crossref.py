from __future__ import annotations

import re
import requests

from ..journal_abbrev import abbreviate_journal
from ..models import Author, Paper

_CROSSREF_API = "https://api.crossref.org/works/"
_HEADERS = {
    "User-Agent": "litman/0.1.0 (mailto:shotaro.tada.m@gmail.com)",
    "Accept": "application/json",
}


def _strip_jats(text: str | None) -> str | None:
    if not text:
        return None
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_year(msg: dict) -> int | None:
    for key in ("published-print", "published-online", "published", "created"):
        parts = msg.get(key, {}).get("date-parts", [[]])
        if parts and parts[0] and parts[0][0]:
            return int(parts[0][0])
    return None


def fetch_by_doi(doi: str, original_url: str) -> Paper:
    resp = requests.get(f"{_CROSSREF_API}{doi}", headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    msg = resp.json()["message"]

    authors = []
    for a in msg.get("author", []):
        authors.append(Author(given=a.get("given", ""), family=a.get("family", "")))

    title_list = msg.get("title", [])
    title = _strip_jats(title_list[0]) if title_list else "Untitled"

    journal_list = msg.get("container-title", [])
    journal = journal_list[0] if journal_list else None

    journal_abbrev = None
    if journal:
        local = abbreviate_journal(journal)
        if local != journal:
            journal_abbrev = local
    if not journal_abbrev:
        short_list = msg.get("short-container-title", [])
        if short_list and short_list[0] != journal:
            journal_abbrev = short_list[0]

    return Paper(
        title=title,
        authors=authors,
        year=_extract_year(msg),
        doi=msg.get("DOI"),
        journal=journal,
        journal_abbrev=journal_abbrev,
        volume=msg.get("volume"),
        issue=msg.get("issue"),
        pages=msg.get("page"),
        publisher=msg.get("publisher"),
        abstract=_strip_jats(msg.get("abstract")),
        url=original_url,
    )
