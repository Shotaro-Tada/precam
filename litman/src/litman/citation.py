from __future__ import annotations

import re

from .models import Author, Paper

STYLES = ["ACS", "Nature", "RSC(JMCA)"]


def _acs_authors(authors: list[Author]) -> str:
    parts = []
    for a in authors:
        if a.given:
            initials = " ".join(g[0] + "." for g in a.given.split() if g)
            parts.append(f"{a.family}, {initials}")
        else:
            parts.append(a.family)
    return "; ".join(parts)


def _nature_authors(authors: list[Author]) -> str:
    parts = []
    for a in authors:
        if a.given:
            initials = " ".join(g[0] + "." for g in a.given.split() if g)
            parts.append(f"{a.family}, {initials}")
        else:
            parts.append(a.family)
    if len(parts) <= 2:
        return " & ".join(parts)
    return ", ".join(parts[:-1]) + " & " + parts[-1]


def _rsc_authors(authors: list[Author]) -> str:
    parts = []
    for a in authors:
        if a.given:
            initials = " ".join(g[0] + "." for g in a.given.split() if g)
            parts.append(f"{initials} {a.family}")
        else:
            parts.append(a.family)
    if len(parts) <= 2:
        return " and ".join(parts)
    return ", ".join(parts[:-1]) + " and " + parts[-1]


AUTHOR_FORMATS = {"ACS": _acs_authors, "Nature": _nature_authors, "RSC": _rsc_authors}


def _journal_name(paper: Paper, abbrev: bool) -> str:
    if abbrev and paper.journal_abbrev:
        return paper.journal_abbrev
    return paper.journal or ""


def format_acs(paper: Paper, with_doi: bool = True, abbrev: bool = False) -> str:
    authors = _acs_authors(paper.authors)
    journal = _journal_name(paper, abbrev)
    vol = f"*{paper.volume}*" if paper.volume else ""
    issue = f" ({paper.issue})" if paper.issue else ""
    pages = f", {paper.pages}" if paper.pages else ""
    year = str(paper.year) if paper.year else ""

    ref = f"{authors} {paper.title}. *{journal}* **{year}**, {vol}{issue}{pages}."
    if with_doi and paper.doi:
        ref += f" DOI: {paper.doi}"
    return ref


def format_nature(paper: Paper, with_doi: bool = True, abbrev: bool = False) -> str:
    authors = _nature_authors(paper.authors)
    journal = _journal_name(paper, abbrev)
    vol = f"**{paper.volume}**" if paper.volume else ""
    pages = f", {paper.pages}" if paper.pages else ""
    year = f"({paper.year})" if paper.year else ""

    ref = f"{authors} {paper.title}. *{journal}* {vol}{pages} {year}."
    if with_doi and paper.doi:
        ref += f" https://doi.org/{paper.doi}"
    return ref


def format_rsc(paper: Paper, with_doi: bool = True, abbrev: bool = False) -> str:
    authors = _rsc_authors(paper.authors)
    journal = _journal_name(paper, abbrev)
    year = str(paper.year) if paper.year else ""
    vol = f"**{paper.volume}**" if paper.volume else ""
    pages = f", {paper.pages}" if paper.pages else ""

    ref = f"{authors}, *{journal}*, {year}, {vol}{pages}."
    if with_doi and paper.doi:
        ref += f" DOI: {paper.doi}"
    return ref


# ── HTML versions (for rich-text clipboard copy) ────────────────────────

def format_acs_html(paper: Paper, with_doi: bool = True, abbrev: bool = False) -> str:
    authors = _acs_authors(paper.authors)
    journal = _journal_name(paper, abbrev)
    vol = f"<i>{paper.volume}</i>" if paper.volume else ""
    issue = f" ({paper.issue})" if paper.issue else ""
    pages = f", {paper.pages}" if paper.pages else ""
    year = str(paper.year) if paper.year else ""

    ref = f"{authors} {paper.title}. <i>{journal}</i> <b>{year}</b>, {vol}{issue}{pages}."
    if with_doi and paper.doi:
        ref += f" DOI: {paper.doi}"
    return ref


def format_nature_html(paper: Paper, with_doi: bool = True, abbrev: bool = False) -> str:
    authors = _nature_authors(paper.authors)
    journal = _journal_name(paper, abbrev)
    vol = f"<b>{paper.volume}</b>" if paper.volume else ""
    pages = f", {paper.pages}" if paper.pages else ""
    year = f"({paper.year})" if paper.year else ""

    ref = f"{authors} {paper.title}. <i>{journal}</i> {vol}{pages} {year}."
    if with_doi and paper.doi:
        ref += f" https://doi.org/{paper.doi}"
    return ref


def format_rsc_html(paper: Paper, with_doi: bool = True, abbrev: bool = False) -> str:
    authors = _rsc_authors(paper.authors)
    journal = _journal_name(paper, abbrev)
    year = str(paper.year) if paper.year else ""
    vol = f"<b>{paper.volume}</b>" if paper.volume else ""
    pages = f", {paper.pages}" if paper.pages else ""

    ref = f"{authors}, <i>{journal}</i>, {year}, {vol}{pages}."
    if with_doi and paper.doi:
        ref += f" DOI: {paper.doi}"
    return ref


_FORMATTERS = {
    "ACS": format_acs,
    "Nature": format_nature,
    "RSC(JMCA)": format_rsc,
}

_FORMATTERS_HTML = {
    "ACS": format_acs_html,
    "Nature": format_nature_html,
    "RSC(JMCA)": format_rsc_html,
}


def format_citation(paper: Paper, style: str, with_doi: bool = True, abbrev: bool = False) -> str:
    fn = _FORMATTERS.get(style)
    if fn is None:
        raise ValueError(f"Unknown style: {style}. Available: {', '.join(STYLES)}")
    return fn(paper, with_doi=with_doi, abbrev=abbrev)


def format_citation_html(paper: Paper, style: str, with_doi: bool = True, abbrev: bool = False) -> str:
    fn = _FORMATTERS_HTML.get(style)
    if fn is None:
        raise ValueError(f"Unknown style: {style}. Available: {', '.join(STYLES)}")
    return fn(paper, with_doi=with_doi, abbrev=abbrev)


# ── Custom style rendering ────────────────────────────────────────────────

def render_custom_style(paper: Paper, style_def: dict, with_doi: bool = True, abbrev: bool = False) -> str:
    author_fn = AUTHOR_FORMATS.get(style_def.get("author_format", "ACS"), _acs_authors)
    authors = author_fn(paper.authors)
    journal = _journal_name(paper, abbrev)

    try:
        ref = style_def["template"].format(
            authors=authors, title=paper.title, journal=journal,
            year=str(paper.year) if paper.year else "",
            volume=paper.volume or "", issue=paper.issue or "",
            pages=paper.pages or "",
        )
    except (KeyError, IndexError):
        ref = f"{authors} {paper.title}."

    if with_doi and paper.doi and style_def.get("doi_template"):
        try:
            ref += style_def["doi_template"].format(doi=paper.doi)
        except (KeyError, IndexError):
            ref += f" DOI: {paper.doi}"
    return ref


def render_custom_style_html(paper: Paper, style_def: dict, with_doi: bool = True, abbrev: bool = False) -> str:
    ref = render_custom_style(paper, style_def, with_doi, abbrev)
    ref = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", ref)
    ref = re.sub(r"\*(.+?)\*", r"<i>\1</i>", ref)
    return ref
