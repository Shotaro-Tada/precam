from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


# =========
# Settings
# =========
ORCID_ID = "0000-0001-5147-4589"
OUT_HTML = Path(__file__).resolve().parents[1] / "site" / "publications.generated.html"
USER_AGENT = "ShotaroTadaWebsite/1.0 (contact: shotaro.tada@zmail.iitm.ac.in)"


def _get_json(url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.json()


def h(s: Optional[str]) -> str:
    return html.escape(s or "")


def norm_doi(d: Optional[str]) -> str:
    if not d:
        return ""
    d = d.strip().lower()
    d = re.sub(r"^https?://(dx\.)?doi\.org/", "", d)
    return d


def norm_title_for_dedup(t: Optional[str]) -> str:
    if not t:
        return ""
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("‐", "-").replace("–", "-").replace("—", "-")
    t = re.sub(r"\s+", " ", t).strip().lower()
    return t


def fetch_orcid_works(orcid_id: str) -> List[Dict[str, Any]]:
    """
    ORCID works summary (grouped). Pick one representative per group to reduce duplicates.
    Prefer DOI > year > title.
    """
    url = f"https://pub.orcid.org/v3.0/{orcid_id}/works"
    headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    data = _get_json(url, headers)

    groups = data.get("group", []) or []
    reps: List[Dict[str, Any]] = []

    for g in groups:
        summaries = g.get("work-summary", []) or []
        if not summaries:
            continue

        candidates: List[Dict[str, Any]] = []

        for s in summaries:
            t = (s.get("title") or {}).get("title") or {}
            title = t.get("value")

            pub_date = s.get("publication-date") or {}
            year = (pub_date.get("year") or {}).get("value")

            doi: Optional[str] = None
            ext_ids = (s.get("external-ids") or {}).get("external-id", []) or []

            for eid in ext_ids:
                if (eid.get("external-id-type") or "").lower() == "doi":
                    doi_val = (eid.get("external-id-value") or "").strip()
                    if doi_val:
                        doi = doi_val
                        break

            if not doi:
                for eid in ext_ids:
                    url_obj = eid.get("external-id-url") or {}
                    u = (url_obj.get("value") or "").strip()
                    m = re.search(r"doi\.org/(10\.\d{4,9}/\S+)", u)
                    if m:
                        doi = m.group(1)
                        break

            candidates.append(
                {
                    "title": title,
                    "year": year,
                    "doi": norm_doi(doi) if doi else None,
                    "type": s.get("type"),
                    "put_code": s.get("put-code"),
                }
            )

        def score(c: Dict[str, Any]):
            has_doi = 1 if c.get("doi") else 0
            has_year = 1 if (c.get("year") and str(c.get("year")).isdigit()) else 0
            has_title = 1 if c.get("title") else 0
            y = int(c["year"]) if (c.get("year") and str(c.get("year")).isdigit()) else -1
            return (has_doi, has_year, y, has_title)

        best = max(candidates, key=score)
        if best.get("title") or best.get("doi"):
            reps.append(best)

    def sort_key(x: Dict[str, Any]):
        y = x.get("year")
        return (-(int(y)) if (y and str(y).isdigit()) else 10**9, (x.get("title") or "").lower())

    reps.sort(key=sort_key)
    return reps


def dedup_final(works: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Final dedup for cases where ORCID groups are split.
    Use (normalized title, year). Prefer entries with DOI.
    """
    seen: Dict[tuple, Dict[str, Any]] = {}

    for w in works:
        year = str(w.get("year") or "").strip()
        key = (norm_title_for_dedup(w.get("title")), year)

        if key not in seen:
            seen[key] = w
            continue

        cur = seen[key]
        cur_has_doi = 1 if cur.get("doi") else 0
        new_has_doi = 1 if w.get("doi") else 0
        if new_has_doi > cur_has_doi:
            seen[key] = w

    tmp = list(seen.values())

    def sort_key(x: Dict[str, Any]):
        y = x.get("year")
        return (-(int(y)) if (y and str(y).isdigit()) else 10**9, (x.get("title") or "").lower())

    tmp.sort(key=sort_key)
    return tmp


def fetch_csl_json(doi: str) -> Optional[Dict[str, Any]]:
    """
    Fetch CSL-JSON via DOI content negotiation.
    """
    doi_n = norm_doi(doi)
    if not doi_n:
        return None

    url = f"https://doi.org/{doi_n}"
    headers = {
        "Accept": "application/vnd.citationstyles.csl+json",
        "User-Agent": USER_AGENT,
    }

    try:
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code != 200:
            return None
        return r.json()
    except (requests.RequestException, json.JSONDecodeError):
        return None


def extract_abstract_text(csl_json: Dict[str, Any]) -> Optional[str]:
    abstract = csl_json.get("abstract")
    if not abstract:
        return None

    text = re.sub(r"<[^>]+>", " ", str(abstract))
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(Abstract\s*)+", "", text, flags=re.IGNORECASE).strip()
    return text or None


def is_shotaro_tada(given: str, family: str) -> bool:
    g = (given or "").strip().lower()
    f = (family or "").strip().lower()
    if f != "tada":
        return False
    # Accept common variants
    return g.startswith("shotaro") or g in {"s.", "s"}


def format_authors_html(csl_json: Dict[str, Any]) -> Optional[str]:
    authors = csl_json.get("author")
    if not authors or not isinstance(authors, list):
        return None

    out: List[str] = []
    for a in authors:
        if not isinstance(a, dict):
            continue
        given = (a.get("given") or "").strip()
        family = (a.get("family") or "").strip()
        if not (given or family):
            continue

        name = f"{given} {family}".strip()
        if is_shotaro_tada(given, family):
            out.append(f"<strong>{h(name)}</strong>")
        else:
            out.append(h(name))

    return ", ".join(out) if out else None


def build_html(works: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    parts.append('<div class="pub-list">')

    for w in works:
        title_raw = w.get("title") or ""
        if title_raw.strip().lower().startswith("correction"):
            continue

        title = re.sub(r"<[^>]+>", "", title_raw or "(untitled)")
        year = w.get("year")
        doi = w.get("doi")
        doi_url = f"https://doi.org/{doi}" if doi else None

        csl = fetch_csl_json(doi) if doi else None
        authors_html = format_authors_html(csl) if csl else None
        abstract = extract_abstract_text(csl) if csl else None

        parts.append('<div class="pub">')
        parts.append(f'  <div class="title">{h(title)}</div>')

        if authors_html:
            parts.append(f'  <div class="authors">{authors_html}</div>')

        meta: List[str] = []
        if year:
            meta.append(h(str(year)))
        if doi_url:
            meta.append(f'<a href="{h(doi_url)}" target="_blank" rel="noopener">DOI</a>')
        if meta:
            parts.append(f'  <div class="detail">{" · ".join(meta)}</div>')

        if abstract:
            parts.append('  <details class="abs">')
            parts.append('    <summary>Abstract</summary>')
            parts.append(f'    <div class="abs-body">{h(abstract)}</div>')
            parts.append('  </details>')

        parts.append("</div>")  # .pub

    parts.append("</div>")  # .pub-list
    return "\n".join(parts)


def main():
    works = fetch_orcid_works(ORCID_ID)
    works = dedup_final(works)
    html_out = build_html(works)

    OUT_HTML.write_text(html_out, encoding="utf-8")
    print(f"Wrote: {OUT_HTML}")


if __name__ == "__main__":
    main()