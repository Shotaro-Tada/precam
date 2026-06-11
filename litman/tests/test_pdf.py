from pathlib import Path

import pytest
import requests
import responses

from litman.fetchers import elsevier, wiley
from litman.models import Author, Paper
from litman.pdf import PdfDownloadError, download_pdf, safe_filename

_PDF_BYTES = b"%PDF-1.5\n%fake pdf body\n%%EOF"


def _paper(**kwargs) -> Paper:
    defaults = dict(title="On the Adsorption of CO2", url="https://doi.org/10.1016/x",
                    authors=[Author(given="G.", family="Busca")], year=1982)
    defaults.update(kwargs)
    return Paper(**defaults)


def test_looks_like_elsevier():
    assert elsevier.looks_like_elsevier("10.1016/0390-6035(82)90059-1")
    assert elsevier.looks_like_elsevier("10.9999/x", publisher="Elsevier BV")
    assert not elsevier.looks_like_elsevier("10.1021/jp057437j")
    assert not elsevier.looks_like_elsevier(None)


def test_safe_filename_from_metadata():
    name = safe_filename(_paper(), "10.1016/x")
    assert name == "Busca-1982-On the Adsorption of CO2.pdf"


def test_safe_filename_fallback_to_doi():
    name = safe_filename(None, "10.1016/abc/def")
    assert name == "10.1016_abc_def.pdf"


@responses.activate
def test_elsevier_download_ok(tmp_path: Path):
    doi = "10.1016/0390-6035(82)90059-1"
    responses.add(
        responses.GET,
        elsevier._ARTICLE_API + requests.utils.quote(doi, safe=""),
        body=_PDF_BYTES, status=200, content_type="application/pdf",
    )
    out = elsevier.download_pdf(doi, tmp_path / "a.pdf", api_key="KEY")
    assert out.read_bytes() == _PDF_BYTES


@responses.activate
def test_elsevier_access_denied(tmp_path: Path):
    doi = "10.1016/x"
    responses.add(
        responses.GET,
        elsevier._ARTICLE_API + requests.utils.quote(doi, safe=""),
        json={"error": "forbidden"}, status=403,
    )
    with pytest.raises(elsevier.ElsevierError, match="Access denied"):
        elsevier.download_pdf(doi, tmp_path / "a.pdf", api_key="KEY")


@responses.activate
def test_elsevier_non_pdf_body(tmp_path: Path):
    doi = "10.1016/x"
    responses.add(
        responses.GET,
        elsevier._ARTICLE_API + requests.utils.quote(doi, safe=""),
        body=b"<xml>error</xml>", status=200,
    )
    with pytest.raises(elsevier.ElsevierError, match="non-PDF"):
        elsevier.download_pdf(doi, tmp_path / "a.pdf", api_key="KEY")


def test_elsevier_no_key(tmp_path: Path):
    with pytest.raises(elsevier.ElsevierError, match="No Elsevier API key"):
        elsevier.download_pdf("10.1016/x", tmp_path / "a.pdf", api_key="")


def test_looks_like_wiley():
    assert wiley.looks_like_wiley("10.1002/anie.200901636")
    assert wiley.looks_like_wiley("10.9999/x", publisher="Wiley-VCH")
    assert not wiley.looks_like_wiley("10.1016/x")
    assert not wiley.looks_like_wiley(None)


@responses.activate
def test_wiley_download_ok(tmp_path: Path):
    doi = "10.1002/anie.200901636"
    responses.add(
        responses.GET,
        wiley._TDM_API + requests.utils.quote(doi, safe=""),
        body=_PDF_BYTES, status=200, content_type="application/pdf",
    )
    out = wiley.download_pdf(doi, tmp_path / "a.pdf", token="TOK")
    assert out.read_bytes() == _PDF_BYTES


@responses.activate
def test_wiley_access_denied(tmp_path: Path):
    doi = "10.1002/x"
    responses.add(
        responses.GET,
        wiley._TDM_API + requests.utils.quote(doi, safe=""),
        json={"error": "forbidden"}, status=403,
    )
    with pytest.raises(wiley.WileyError, match="Access denied"):
        wiley.download_pdf(doi, tmp_path / "a.pdf", token="TOK")


def test_wiley_no_token(tmp_path: Path):
    with pytest.raises(wiley.WileyError, match="No Wiley TDM token"):
        wiley.download_pdf("10.1002/x", tmp_path / "a.pdf", token="")


@responses.activate
def test_download_pdf_routes_to_wiley(tmp_path: Path):
    doi = "10.1002/anie.200901636"
    responses.add(
        responses.GET,
        wiley._TDM_API + requests.utils.quote(doi, safe=""),
        body=_PDF_BYTES, status=200, content_type="application/pdf",
    )
    path, route = download_pdf(
        doi, tmp_path, paper=_paper(doi=doi), wiley_tdm_token="TOK",
    )
    assert route == "wiley"
    assert path.read_bytes() == _PDF_BYTES


@responses.activate
def test_download_pdf_routes_to_elsevier(tmp_path: Path):
    doi = "10.1016/0390-6035(82)90059-1"
    responses.add(
        responses.GET,
        elsevier._ARTICLE_API + requests.utils.quote(doi, safe=""),
        body=_PDF_BYTES, status=200, content_type="application/pdf",
    )
    path, route = download_pdf(
        doi, tmp_path, paper=_paper(doi=doi), elsevier_api_key="KEY",
    )
    assert route == "elsevier"
    assert path.name == "Busca-1982-On the Adsorption of CO2.pdf"
    assert path.read_bytes() == _PDF_BYTES


@responses.activate
def test_download_pdf_unpaywall_fallback(tmp_path: Path):
    doi = "10.1038/ncomms15266"  # non-Elsevier
    responses.add(
        responses.GET,
        "https://api.unpaywall.org/v2/" + requests.utils.quote(doi, safe=""),
        json={"best_oa_location": {"url_for_pdf": "https://oa.example/p.pdf"}},
        status=200,
    )
    responses.add(responses.GET, "https://oa.example/p.pdf",
                  body=_PDF_BYTES, status=200, content_type="application/pdf")
    path, route = download_pdf(
        doi, tmp_path / "z.pdf", unpaywall_email="me@example.com",
    )
    assert route == "unpaywall"
    assert path.read_bytes() == _PDF_BYTES


def test_download_pdf_no_routes(tmp_path: Path):
    with pytest.raises(PdfDownloadError, match="Could not download"):
        download_pdf("10.1021/jp057437j", tmp_path / "z.pdf")
