from __future__ import annotations

import re

import requests
from bs4 import BeautifulSoup

from ..models import Author, Paper

_HEADERS = {
    "User-Agent": "litman/0.1.0 (Mozilla/5.0 compatible; mailto:shotaro.tada.m@gmail.com)",
    "Accept": "text/html,application/xhtml+xml",
}


def _meta(soup: BeautifulSoup, names: list[str]) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"name": name}) or soup.find(
            "meta", attrs={"property": name}
        )
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _meta_all(soup: BeautifulSoup, name: str) -> list[str]:
    tags = soup.find_all("meta", attrs={"name": name})
    return [t["content"].strip() for t in tags if t.get("content")]


def _parse_authors(soup: BeautifulSoup) -> list[Author]:
    raw = _meta_all(soup, "citation_author") or _meta_all(soup, "DC.creator")
    authors = []
    for name in raw:
        if "," in name:
            parts = [p.strip() for p in name.split(",", 1)]
            authors.append(Author(family=parts[0], given=parts[1] if len(parts) > 1 else ""))
        else:
            parts = name.rsplit(" ", 1)
            if len(parts) == 2:
                authors.append(Author(given=parts[0], family=parts[1]))
            else:
                authors.append(Author(family=parts[0]))
    return authors


def _extract_year(soup: BeautifulSoup) -> int | None:
    date_str = _meta(soup, ["citation_publication_date", "citation_date", "DC.date"])
    if date_str:
        m = re.search(r"(\d{4})", date_str)
        if m:
            return int(m.group(1))
    return None


def fetch_from_page(url: str) -> Paper:
    resp = requests.get(url, headers=_HEADERS, timeout=15, allow_redirects=True)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    title = (
        _meta(soup, ["citation_title", "DC.title", "og:title"])
        or (soup.title.string.strip() if soup.title and soup.title.string else "Untitled")
    )
    doi = _meta(soup, ["citation_doi", "DC.identifier"])
    if doi and not doi.startswith("10."):
        doi = None

    return Paper(
        title=title,
        authors=_parse_authors(soup),
        year=_extract_year(soup),
        doi=doi,
        journal=_meta(soup, ["citation_journal_title", "citation_conference_title"]),
        volume=_meta(soup, ["citation_volume"]),
        issue=_meta(soup, ["citation_issue"]),
        pages=_meta(soup, ["citation_firstpage"]),
        publisher=_meta(soup, ["citation_publisher", "DC.publisher"]),
        abstract=_meta(soup, ["citation_abstract", "DC.description", "description", "og:description"]),
        url=url,
    )
