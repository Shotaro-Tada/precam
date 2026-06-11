from __future__ import annotations

import re
from pathlib import Path

import requests

from .fetchers import elsevier, wiley
from .models import Paper

_HEADERS = {"User-Agent": "litman/1.0.0 (mailto:shotaro.tada.m@gmail.com)"}
_UNPAYWALL_API = "https://api.unpaywall.org/v2/"


class PdfDownloadError(RuntimeError):
    """Raised when no route could produce a PDF for a DOI."""


def safe_filename(paper: Paper | None, doi: str) -> str:
    """Build a reference-style filename: ``Family-Year-Title.pdf``.

    Falls back to the DOI (slashes replaced) when no metadata is available.
    """
    if paper and paper.authors:
        family = re.sub(r"[^A-Za-z0-9]", "", paper.authors[0].family) or "unknown"
        year = str(paper.year) if paper.year else "nd"
        title = re.sub(r"[<>:\"/\\|?*]", "", (paper.title or "")).strip()
        title = re.sub(r"\s+", " ", title)[:120]
        return f"{family}-{year}-{title}.pdf".rstrip()
    return re.sub(r"[<>:\"/\\|?*]", "_", doi) + ".pdf"


def _download_oa(doi: str, dest: Path, unpaywall_email: str, timeout: int) -> Path:
    """Try the open-access PDF that Unpaywall reports for ``doi``."""
    resp = requests.get(
        _UNPAYWALL_API + requests.utils.quote(doi, safe=""),
        params={"email": unpaywall_email},
        headers=_HEADERS,
        timeout=timeout,
    )
    resp.raise_for_status()
    loc = (resp.json() or {}).get("best_oa_location") or {}
    pdf_url = loc.get("url_for_pdf")
    if not pdf_url:
        raise PdfDownloadError(f"Unpaywall found no open-access PDF for DOI {doi}.")

    pdf = requests.get(pdf_url, headers=_HEADERS, timeout=timeout)
    pdf.raise_for_status()
    if not pdf.content.startswith(b"%PDF"):
        raise PdfDownloadError(
            f"The open-access link for {doi} did not return a PDF ({pdf_url})."
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(pdf.content)
    return dest


def download_pdf(
    doi: str,
    dest: str | Path,
    *,
    paper: Paper | None = None,
    elsevier_api_key: str | None = None,
    elsevier_insttoken: str | None = None,
    wiley_tdm_token: str | None = None,
    unpaywall_email: str | None = None,
    timeout: int = 60,
) -> tuple[Path, str]:
    """Fetch a PDF for ``doi`` and return ``(path, route)``.

    Route order: the matching publisher TDM API for Elsevier- or Wiley-
    registered DOIs (the cases the Chrome extension handles poorly), then an
    Unpaywall open-access fallback for everything else. Subscription content
    from publishers without a programmatic API (ACS, RSC) is out of scope here
    and is left to the browser extension.
    """
    dest = Path(dest)
    if dest.is_dir() or str(dest).endswith(("/", "\\")):
        dest = dest / safe_filename(paper, doi)

    publisher = paper.publisher if paper else None
    errors: list[str] = []

    if elsevier.looks_like_elsevier(doi, publisher):
        if elsevier_api_key:
            try:
                out = elsevier.download_pdf(
                    doi, dest, elsevier_api_key, elsevier_insttoken, timeout=timeout
                )
                return out, "elsevier"
            except elsevier.ElsevierError as e:
                errors.append(f"elsevier: {e}")
        else:
            errors.append("elsevier: no API key configured")

    if wiley.looks_like_wiley(doi, publisher):
        if wiley_tdm_token:
            try:
                out = wiley.download_pdf(doi, dest, wiley_tdm_token, timeout=timeout)
                return out, "wiley"
            except wiley.WileyError as e:
                errors.append(f"wiley: {e}")
        else:
            errors.append("wiley: no TDM token configured")

    if unpaywall_email:
        try:
            out = _download_oa(doi, dest, unpaywall_email, timeout=timeout)
            return out, "unpaywall"
        except (PdfDownloadError, requests.RequestException) as e:
            errors.append(f"unpaywall: {e}")
    else:
        errors.append("unpaywall: no email configured")

    raise PdfDownloadError(
        "Could not download a PDF for DOI "
        f"{doi}. Tried:\n  - " + "\n  - ".join(errors)
    )
