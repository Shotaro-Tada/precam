from __future__ import annotations

import re
from pathlib import Path

import requests

from .models import Paper

_HEADERS = {"User-Agent": "litman/0.1.0 (mailto:shotaro.tada.m@gmail.com)"}


def fetch_bibtex_from_doi(doi: str) -> str | None:
    try:
        resp = requests.get(
            f"https://doi.org/{doi}",
            headers={**_HEADERS, "Accept": "application/x-bibtex"},
            timeout=15,
            allow_redirects=True,
        )
        if resp.status_code == 200 and "@" in resp.text:
            return resp.text.strip()
    except requests.RequestException:
        pass
    return None


def _escape_latex(s: str) -> str:
    for ch in ("&", "%", "#", "_"):
        s = s.replace(ch, f"\\{ch}")
    return s


def paper_to_bibtex(paper: Paper) -> str:
    key = paper.bibtex_key or "unknown"
    authors_str = " and ".join(
        f"{a.family}, {a.given}" if a.given else a.family for a in paper.authors
    )
    lines = [f"@article{{{key},"]
    if paper.title:
        lines.append(f"  title = {{{_escape_latex(paper.title)}}},")
    if authors_str:
        lines.append(f"  author = {{{_escape_latex(authors_str)}}},")
    if paper.year:
        lines.append(f"  year = {{{paper.year}}},")
    if paper.journal:
        lines.append(f"  journal = {{{_escape_latex(paper.journal)}}},")
    if paper.volume:
        lines.append(f"  volume = {{{paper.volume}}},")
    if paper.issue:
        lines.append(f"  number = {{{paper.issue}}},")
    if paper.pages:
        lines.append(f"  pages = {{{paper.pages}}},")
    if paper.doi:
        lines.append(f"  doi = {{{paper.doi}}},")
    if paper.url:
        lines.append(f"  url = {{{paper.url}}},")
    lines.append("}")
    return "\n".join(lines)


def _replace_key(bibtex: str, new_key: str) -> str:
    return re.sub(r"@(\w+)\{[^,]+,", rf"@\1{{{new_key},", bibtex, count=1)


def generate_bibtex(paper: Paper) -> str:
    if paper.doi:
        bib = fetch_bibtex_from_doi(paper.doi)
        if bib and paper.bibtex_key:
            return _replace_key(bib, paper.bibtex_key)
        if bib:
            return bib
    return paper_to_bibtex(paper)


def export_library_bib(papers: list[Paper], output_path: Path) -> None:
    entries = []
    for paper in papers:
        entries.append(generate_bibtex(paper))
    output_path.write_text("\n\n".join(entries) + "\n", encoding="utf-8")
