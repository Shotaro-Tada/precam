from __future__ import annotations

from pathlib import Path

import requests

_TDM_API = "https://api.wiley.com/onlinelibrary/tdm/v1/articles/"
_HEADERS_BASE = {"User-Agent": "litman/1.0.0 (mailto:shotaro.tada.m@gmail.com)"}

# DOI registrant prefixes routinely served on Wiley Online Library.
WILEY_DOI_PREFIXES = (
    "10.1002",  # Wiley core (Angew. Chem., Adv. Mater., …)
    "10.1111",  # Blackwell
    "10.1046",
    "10.1034",
    "10.1049",  # IET (hosted by Wiley)
)


class WileyError(RuntimeError):
    """Raised when the Wiley TDM API cannot return a PDF."""


def looks_like_wiley(doi: str | None, publisher: str | None = None) -> bool:
    if publisher and "wiley" in publisher.lower():
        return True
    if doi:
        prefix = doi.split("/", 1)[0]
        return prefix in WILEY_DOI_PREFIXES
    return False


def download_pdf(
    doi: str,
    dest: str | Path,
    token: str,
    timeout: int = 60,
) -> Path:
    """Download a full-text PDF for ``doi`` via the Wiley TDM API.

    Entitlement is decided by Wiley from the Clickthrough client token (obtained
    via ORCID after accepting the Wiley TDM licence) combined with the caller's
    institutional IP range. The token is sent in the ``Wiley-TDM-Client-Token``
    header; the endpoint answers with a redirect to the PDF, which requests
    follows automatically.

    Raises WileyError on a missing token, an access/entitlement failure, or a
    response body that is not a PDF.
    """
    if not token:
        raise WileyError(
            "No Wiley TDM token. Obtain one via ORCID at "
            "https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining "
            "and set it with `litman set-config wiley_tdm_token <TOKEN>` or the "
            "WILEY_TDM_TOKEN environment variable."
        )

    headers = dict(_HEADERS_BASE)
    headers["Wiley-TDM-Client-Token"] = token
    headers["Accept"] = "application/pdf"

    url = _TDM_API + requests.utils.quote(doi, safe="")
    resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)

    if resp.status_code in (401, 403):
        raise WileyError(
            f"Access denied by Wiley (HTTP {resp.status_code}). The token may be "
            "invalid or expired, or this article is not entitled from the current "
            "IP. Run from the institutional network."
        )
    if resp.status_code == 404:
        raise WileyError(f"Wiley has no full text for DOI {doi} (HTTP 404).")
    resp.raise_for_status()

    content = resp.content
    if not content.startswith(b"%PDF"):
        snippet = content[:200].decode("utf-8", errors="replace").strip()
        raise WileyError(
            f"Wiley returned a non-PDF response for DOI {doi}. "
            f"First bytes: {snippet!r}"
        )

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return dest
