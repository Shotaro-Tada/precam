from __future__ import annotations

import re
from pathlib import Path

from .models import Author, Paper


def _strip_braces(s: str) -> str:
    s = s.strip()
    if s.startswith("{") and s.endswith("}"):
        s = s[1:-1]
    return s


def _strip_latex(s: str) -> str:
    s = re.sub(r"\\textit\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\\textrm\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\$[^$]*\$", "", s)
    s = re.sub(r"\{\\[a-zA-Z]+\s+([^}]*)\}", r"\1", s)
    s = re.sub(r"[{}]", "", s)
    s = re.sub(r"\\&", "&", s)
    s = re.sub(r"\\[a-zA-Z]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_authors_bib(raw: str) -> list[Author]:
    raw = _strip_braces(raw)
    parts = re.split(r"\s+and\s+", raw)
    authors = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        part = re.sub(r"[{}]", "", part)
        if "," in part:
            tokens = [t.strip() for t in part.split(",", 1)]
            authors.append(Author(family=tokens[0], given=tokens[1] if len(tokens) > 1 else ""))
        else:
            tokens = part.rsplit(" ", 1)
            if len(tokens) == 2:
                authors.append(Author(given=tokens[0], family=tokens[1]))
            else:
                authors.append(Author(family=tokens[0]))
    return authors


def _extract_year(fields: dict) -> int | None:
    raw = fields.get("year", "")
    m = re.search(r"(\d{4})", raw)
    return int(m.group(1)) if m else None


def parse_bibtex_file(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")

    entries = []
    entry_re = re.compile(r"@(\w+)\{([^,]*),", re.MULTILINE)

    positions = [(m.start(), m.group(1), m.group(2).strip()) for m in entry_re.finditer(text)]

    for i, (start, entry_type, cite_key) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(text)
        block = text[start:end]

        brace_depth = 0
        body_start = block.index("{") + 1
        body_end = len(block)
        for j in range(body_start, len(block)):
            if block[j] == "{":
                brace_depth += 1
            elif block[j] == "}":
                if brace_depth == 0:
                    body_end = j
                    break
                brace_depth -= 1

        body = block[body_start:body_end]
        first_comma = body.index(",") + 1 if "," in body else 0
        body = body[first_comma:]

        fields = {}
        field_re = re.compile(r"(\w+)\s*=\s*", re.MULTILINE)
        field_matches = list(field_re.finditer(body))

        for k, fm in enumerate(field_matches):
            field_name = fm.group(1).lower()
            value_start = fm.end()

            if k + 1 < len(field_matches):
                value_end = field_matches[k + 1].start()
            else:
                value_end = len(body)

            raw_value = body[value_start:value_end].strip()
            raw_value = raw_value.rstrip(",").strip()

            if raw_value.startswith("{"):
                depth = 0
                for ci, ch in enumerate(raw_value):
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            raw_value = raw_value[1:ci]
                            break
            elif raw_value.startswith('"'):
                end_q = raw_value.find('"', 1)
                if end_q > 0:
                    raw_value = raw_value[1:end_q]

            fields[field_name] = raw_value.strip()

        entries.append({
            "type": entry_type.lower(),
            "cite_key": cite_key,
            "fields": fields,
        })

    return entries


def bibtex_to_papers(path: Path) -> list[Paper]:
    entries = parse_bibtex_file(path)
    papers = []

    for entry in entries:
        fields = entry["fields"]

        title_raw = fields.get("title", "Untitled")
        title = _strip_latex(_strip_braces(title_raw))
        if not title:
            title = "Untitled"

        authors = _parse_authors_bib(fields.get("author", ""))

        doi = fields.get("doi", "").strip()
        if doi:
            doi = re.sub(r"[{}]", "", doi)

        url = fields.get("url", "").strip()
        if not url and doi:
            url = f"https://doi.org/{doi}"
        if not url:
            url = ""
        url = re.sub(r"[{}]", "", url)

        journal = _strip_latex(_strip_braces(fields.get("journal", "")))
        if not journal:
            journal = _strip_latex(_strip_braces(fields.get("booktitle", "")))

        keywords_raw = fields.get("keywords", "")
        tags = [t.strip() for t in keywords_raw.split(",") if t.strip()] if keywords_raw else []

        pages = fields.get("pages", "").replace("--", "–")

        paper = Paper(
            title=title,
            authors=authors,
            year=_extract_year(fields),
            doi=doi or None,
            journal=journal or None,
            volume=fields.get("volume"),
            issue=fields.get("number"),
            pages=pages or None,
            publisher=_strip_latex(_strip_braces(fields.get("publisher", ""))) or None,
            abstract=_strip_braces(fields.get("abstract", "")) or None,
            url=url,
            tags=tags,
            bibtex_key=entry["cite_key"],
        )
        papers.append(paper)

    return papers
