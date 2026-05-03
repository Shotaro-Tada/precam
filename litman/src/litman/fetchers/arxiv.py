from __future__ import annotations

import xml.etree.ElementTree as ET

import requests

from ..models import Author, Paper

_ARXIV_API = "https://export.arxiv.org/api/query"
_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
_HEADERS = {"User-Agent": "litman/0.1.0 (mailto:shotaro.tada.m@gmail.com)"}


def _parse_authors(entry: ET.Element) -> list[Author]:
    authors = []
    for author_el in entry.findall("atom:author", _NS):
        name_el = author_el.find("atom:name", _NS)
        if name_el is None or not name_el.text:
            continue
        parts = name_el.text.strip().rsplit(" ", 1)
        if len(parts) == 2:
            authors.append(Author(given=parts[0], family=parts[1]))
        else:
            authors.append(Author(family=parts[0]))
    return authors


def _extract_year(entry: ET.Element) -> int | None:
    pub = entry.find("atom:published", _NS)
    if pub is not None and pub.text:
        return int(pub.text[:4])
    return None


def _extract_doi(entry: ET.Element) -> str | None:
    doi_el = entry.find("arxiv:doi", _NS)
    if doi_el is not None and doi_el.text:
        return doi_el.text.strip()
    return None


def fetch_by_id(arxiv_id: str, original_url: str) -> Paper:
    resp = requests.get(
        _ARXIV_API, params={"id_list": arxiv_id}, headers=_HEADERS, timeout=15
    )
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    entry = root.find("atom:entry", _NS)
    if entry is None:
        raise ValueError(f"No entry found for arXiv ID: {arxiv_id}")

    title_el = entry.find("atom:title", _NS)
    title = title_el.text.strip().replace("\n", " ") if title_el is not None and title_el.text else "Untitled"

    summary_el = entry.find("atom:summary", _NS)
    abstract = summary_el.text.strip() if summary_el is not None and summary_el.text else None

    cat_el = entry.find("arxiv:primary_category", _NS)
    category = cat_el.get("term") if cat_el is not None else None

    return Paper(
        title=title,
        authors=_parse_authors(entry),
        year=_extract_year(entry),
        doi=_extract_doi(entry),
        arxiv_id=arxiv_id,
        journal=f"arXiv:{category}" if category else "arXiv",
        abstract=abstract,
        url=original_url,
    )
