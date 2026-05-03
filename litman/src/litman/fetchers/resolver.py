from __future__ import annotations

import re

import requests

from ..models import Paper
from . import arxiv, crossref, html_meta

_DOI_URL_RE = re.compile(r"(?:https?://)?(?:dx\.)?doi\.org/(10\.\d{4,}/\S+)", re.IGNORECASE)
_DOI_IN_PATH_RE = re.compile(r"/(?:doi/(?:full|abs|epdf|pdf|book)?/?)?(10\.\d{4,}/[^\s?#]+)", re.IGNORECASE)
_ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)", re.IGNORECASE)

_SCIENCEDIRECT_PII_RE = re.compile(
    r"sciencedirect\.com/science/article/(?:pii|abs)/([A-Z0-9]+)", re.IGNORECASE
)
_ELSEVIER_DOMAINS = (
    "sciencedirect.com",
    "linkinghub.elsevier.com",
)

_CROSSREF_HEADERS = {
    "User-Agent": "litman/0.1.0 (mailto:shotaro.tada.m@gmail.com)",
}


def _extract_doi_from_url(url: str) -> str | None:
    m = _DOI_URL_RE.search(url)
    if m:
        return m.group(1).rstrip(".")
    m = _DOI_IN_PATH_RE.search(url)
    if m:
        return m.group(1).rstrip(".")
    return None


def _extract_arxiv_id(url: str) -> str | None:
    m = _ARXIV_RE.search(url)
    return m.group(1) if m else None


def _is_elsevier(url: str) -> bool:
    return any(d in url.lower() for d in _ELSEVIER_DOMAINS)


def _resolve_pii_to_doi(pii: str) -> str | None:
    """Use CrossRef search to find DOI from Elsevier PII."""
    try:
        resp = requests.get(
            "https://api.crossref.org/works",
            params={"filter": f"alternative-id:{pii}", "rows": "1"},
            headers=_CROSSREF_HEADERS,
            timeout=15,
        )
        if resp.ok:
            items = resp.json().get("message", {}).get("items", [])
            if items:
                return items[0].get("DOI")
    except requests.RequestException:
        pass

    try:
        resp = requests.get(
            "https://api.crossref.org/works",
            params={"query": pii, "rows": "1"},
            headers=_CROSSREF_HEADERS,
            timeout=15,
        )
        if resp.ok:
            items = resp.json().get("message", {}).get("items", [])
            if items:
                return items[0].get("DOI")
    except requests.RequestException:
        pass

    return None


def _try_elsevier(url: str) -> Paper | None:
    """Handle ScienceDirect / Elsevier URLs that block scraping."""
    m = _SCIENCEDIRECT_PII_RE.search(url)
    if m:
        pii = m.group(1)
        doi = _resolve_pii_to_doi(pii)
        if doi:
            return crossref.fetch_by_doi(doi, url)

    try:
        paper = html_meta.fetch_from_page(url)
        if paper.doi:
            return crossref.fetch_by_doi(paper.doi, url)
        return paper
    except requests.HTTPError:
        pass

    return None


def fetch_metadata(url: str) -> Paper:
    doi = _extract_doi_from_url(url)
    if doi:
        return crossref.fetch_by_doi(doi, url)

    arxiv_id = _extract_arxiv_id(url)
    if arxiv_id:
        return arxiv.fetch_by_id(arxiv_id, url)

    if _is_elsevier(url):
        paper = _try_elsevier(url)
        if paper:
            return paper

    try:
        paper = html_meta.fetch_from_page(url)
    except requests.HTTPError:
        raise ValueError(
            f"Could not access {url}. Try using a DOI URL instead: https://doi.org/10.xxxx/..."
        )

    if paper.doi:
        try:
            enriched = crossref.fetch_by_doi(paper.doi, url)
            enriched.id = paper.id
            return enriched
        except Exception:
            pass

    return paper
