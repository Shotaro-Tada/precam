from __future__ import annotations

from .models import Paper


def _paper_text(paper: Paper) -> str:
    parts = [
        paper.title,
        paper.journal or "",
        paper.abstract or "",
        paper.notes,
        " ".join(paper.tags),
        " ".join(a.full_name() for a in paper.authors),
        str(paper.year) if paper.year else "",
        paper.doi or "",
    ]
    return " ".join(parts).lower()


def search_papers(papers: list[Paper], query: str) -> list[Paper]:
    tokens = query.lower().split()
    results = []
    for paper in papers:
        text = _paper_text(paper)
        if all(t in text for t in tokens):
            results.append(paper)
    return results


def filter_papers(
    papers: list[Paper],
    year_from: int | None = None,
    year_to: int | None = None,
    tags: list[str] | None = None,
    journal: str | None = None,
) -> list[Paper]:
    result = papers
    if year_from is not None:
        result = [p for p in result if p.year and p.year >= year_from]
    if year_to is not None:
        result = [p for p in result if p.year and p.year <= year_to]
    if tags:
        tag_set = {t.lower() for t in tags}
        result = [p for p in result if tag_set & {t.lower() for t in p.tags}]
    if journal:
        jl = journal.lower()
        result = [p for p in result if p.journal and jl in p.journal.lower()]
    return result
