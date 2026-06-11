from __future__ import annotations

from pathlib import Path

import requests

_ARTICLE_API = "https://api.elsevier.com/content/article/doi/"
_HEADERS_BASE = {"User-Agent": "litman/1.0.0 (mailto:shotaro.tada.m@gmail.com)"}

# DOI registrant prefixes routinely served by Elsevier / ScienceDirect.
ELSEVIER_DOI_PREFIXES = ("10.1016", "10.1006", "10.1053", "10.1067", "10.5555")


class ElsevierError(RuntimeError):
    """Raised when the Elsevier Article Retrieval API cannot return a PDF."""


def looks_like_elsevier(doi: str | None, publisher: str | None = None) -> bool:
    if publisher and "elsevier" in publisher.lower():
        return True
    if doi:
        prefix = doi.split("/", 1)[0]
        return prefix in ELSEVIER_DOI_PREFIXES
    return False


def download_pdf(
    doi: str,
    dest: str | Path,
    api_key: str,
    insttoken: str | None = None,
    timeout: int = 60,
) -> Path:
    """Download a full-text PDF for ``doi`` via the Elsevier Article Retrieval API.

    Entitlement is decided by Elsevier from the API key plus either the caller's
    IP range (institutional network) or an institutional token. The key is sent
    in the ``X-ELS-APIKey`` header; ``Accept: application/pdf`` requests the PDF
    representation rather than the default XML.

    Raises ElsevierError on missing key, an access/entitlement failure, or a
    response body that is not a PDF (the API answers errors as JSON/XML with a
    200-ish status in some cases, so the magic bytes are checked).
    """
    if not api_key:
        raise ElsevierError(
            "No Elsevier API key. Get one at https://dev.elsevier.com/ and set it "
            "with `litman set-config elsevier_api_key <KEY>` or the ELSEVIER_API_KEY "
            "environment variable."
        )

    headers = dict(_HEADERS_BASE)
    headers["X-ELS-APIKey"] = api_key
    headers["Accept"] = "application/pdf"
    if insttoken:
        headers["X-ELS-Insttoken"] = insttoken

    url = _ARTICLE_API + requests.utils.quote(doi, safe="")
    resp = requests.get(url, headers=headers, timeout=timeout)

    if resp.status_code in (401, 403):
        raise ElsevierError(
            f"Access denied by Elsevier (HTTP {resp.status_code}). The key may be "
            "invalid, or this article is not entitled from the current IP / token. "
            "Run from the institutional network or supply an insttoken."
        )
    if resp.status_code == 404:
        raise ElsevierError(f"Elsevier has no full text for DOI {doi} (HTTP 404).")
    resp.raise_for_status()

    content = resp.content
    if not content.startswith(b"%PDF"):
        # The API returned an error document (XML/JSON) with a non-PDF body.
        snippet = content[:200].decode("utf-8", errors="replace").strip()
        raise ElsevierError(
            f"Elsevier returned a non-PDF response for DOI {doi}. "
            f"First bytes: {snippet!r}"
        )

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return dest
