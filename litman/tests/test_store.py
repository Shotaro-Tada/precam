import json
from pathlib import Path

from litman.models import Author, Paper
from litman.store import (
    delete_paper,
    find_duplicate,
    load_all_papers,
    load_paper,
    save_paper,
)


def _make_paper(**kwargs) -> Paper:
    defaults = dict(title="Test", url="https://example.com")
    defaults.update(kwargs)
    return Paper(**defaults)


def test_save_and_load(tmp_path: Path):
    p = _make_paper(title="Alpha Paper", doi="10.1234/alpha")
    save_paper(p, tmp_path)

    loaded = load_paper(p.id, tmp_path)
    assert loaded.title == "Alpha Paper"
    assert loaded.doi == "10.1234/alpha"


def test_load_all(tmp_path: Path):
    for i in range(3):
        save_paper(_make_paper(title=f"Paper {i}"), tmp_path)

    all_papers = load_all_papers(tmp_path)
    assert len(all_papers) == 3


def test_delete(tmp_path: Path):
    p = _make_paper()
    save_paper(p, tmp_path)
    delete_paper(p.id, tmp_path)
    assert load_all_papers(tmp_path) == []


def test_find_duplicate_by_doi(tmp_path: Path):
    p = _make_paper(doi="10.1234/dup")
    save_paper(p, tmp_path)

    found = find_duplicate("10.1234/dup", "https://other.com", tmp_path)
    assert found is not None
    assert found.id == p.id


def test_find_duplicate_by_url(tmp_path: Path):
    p = _make_paper(url="https://example.com/paper1")
    save_paper(p, tmp_path)

    found = find_duplicate(None, "https://example.com/paper1", tmp_path)
    assert found is not None


def test_json_is_sorted_and_readable(tmp_path: Path):
    p = _make_paper(title="Readable JSON Test")
    path = save_paper(p, tmp_path)
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    keys = list(data.keys())
    assert keys == sorted(keys)
    assert text.endswith("\n")
