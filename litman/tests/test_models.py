from litman.models import Author, Paper


def test_author_full_name():
    a = Author(given="Shotaro", family="Tada")
    assert a.full_name() == "Shotaro Tada"


def test_author_family_only():
    a = Author(family="Tada")
    assert a.full_name() == "Tada"


def test_paper_bibtex_key_auto():
    p = Paper(
        title="Construction of Metal-Organic Nanostructures",
        authors=[Author(given="Shotaro", family="Tada")],
        year=2023,
        url="https://example.com",
    )
    assert p.bibtex_key == "tada2023construction"


def test_paper_bibtex_key_no_author():
    p = Paper(title="Some Title", url="https://example.com")
    assert p.bibtex_key.startswith("unknown")


def test_paper_roundtrip():
    p = Paper(
        title="Test Paper",
        authors=[Author(given="A", family="B")],
        year=2025,
        doi="10.1234/test",
        url="https://example.com",
        tags=["cat", "dft"],
    )
    data = p.model_dump()
    p2 = Paper.model_validate(data)
    assert p2.title == p.title
    assert p2.tags == p.tags
    assert p2.id == p.id
