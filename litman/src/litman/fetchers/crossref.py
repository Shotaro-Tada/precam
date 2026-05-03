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
    text = re.sub(r"<(?:jats:)?sup>([^<]*)</(?:jats:)?sup>", r"^\1", text)
    text = re.sub(r"<(?:jats:)?sub>([^<]*)</(?:jats:)?sub>", r"\1", text)
    text = re.sub(r"<(?:jats:)?p>", " ", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"^Abstract\s*", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _extract_year(msg: dict) -> int | None:
    for key in ("published-print", "published-online", "published", "created"):
        parts = msg.get(key, {}).get("date-parts", [[]])
        if parts and parts[0] and parts[0][0]:
            return int(parts[0][0])
    return None


def search_doi_by_title(title: str, rows: int = 5) -> list[dict]:
    resp = requests.get(
        "https://api.crossref.org/works",
        params={"query.title": title, "rows": rows, "select": "DOI,title,author,published,container-title"},
        headers=_HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    results = []
    for item in resp.json().get("message", {}).get("items", []):
        t = item.get("title", [""])[0] if item.get("title") else ""
        authors = [f"{a.get('given', '')} {a.get('family', '')}" for a in item.get("author", [])[:3]]
        year = None
        for key in ("published", "published-print", "published-online"):
            parts = item.get(key, {}).get("date-parts", [[]])
            if parts and parts[0] and parts[0][0]:
                year = int(parts[0][0])
                break
        journal = (item.get("container-title") or [""])[0]
        results.append({"doi": item.get("DOI", ""), "title": t, "authors": authors, "year": year, "journal": journal})
    return results


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
