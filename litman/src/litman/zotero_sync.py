from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import Paper
from .store import load_all_papers, save_paper, get_library_dir


def _build_collection_tree(db: sqlite3.Connection) -> dict[int, str]:
    """Build collectionID -> full path name (e.g. '@2025_PDC/Tm-PDCs')."""
    rows = db.execute(
        "SELECT collectionID, collectionName, parentCollectionID FROM collections"
    ).fetchall()

    name_map = {}
    parent_map = {}
    for cid, cname, pid in rows:
        name_map[cid] = cname
        parent_map[cid] = pid

    full_path: dict[int, str] = {}

    def resolve(cid: int) -> str:
        if cid in full_path:
            return full_path[cid]
        pid = parent_map.get(cid)
        if pid is None:
            full_path[cid] = name_map[cid]
        else:
            full_path[cid] = resolve(pid) + "/" + name_map[cid]
        return full_path[cid]

    for cid in name_map:
        resolve(cid)

    return full_path


def _build_item_collections(db: sqlite3.Connection, collection_tree: dict[int, str]) -> dict[int, list[str]]:
    """Build itemID -> list of collection full paths."""
    rows = db.execute("SELECT collectionID, itemID FROM collectionItems").fetchall()
    result: dict[int, list[str]] = {}
    for cid, iid in rows:
        path = collection_tree.get(cid)
        if path:
            result.setdefault(iid, []).append(path)
    return result


def _build_item_identifiers(db: sqlite3.Connection) -> dict[int, dict[str, str]]:
    """Build itemID -> {doi, url} mapping."""
    rows = db.execute("""
        SELECT i.itemID, f.fieldName, v.value
        FROM items i
        JOIN itemData d ON d.itemID = i.itemID
        JOIN fields f ON f.fieldID = d.fieldID
        JOIN itemDataValues v ON v.valueID = d.valueID
        WHERE f.fieldName IN ('DOI', 'url')
    """).fetchall()

    result: dict[int, dict[str, str]] = {}
    for iid, fname, val in rows:
        result.setdefault(iid, {})[fname.lower()] = val
    return result


def sync_collections(
    zotero_db_path: Path,
    library_dir: Path | None = None,
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Read Zotero SQLite and add collection paths as 'folder:...' tags to litman papers.
    Returns (updated_count, unmatched_count).
    """
    lib = get_library_dir(library_dir)
    papers = load_all_papers(lib)

    doi_index: dict[str, Paper] = {}
    url_index: dict[str, Paper] = {}
    for p in papers:
        if p.doi:
            doi_index[p.doi.lower()] = p
        if p.url:
            url_index[p.url] = p

    db = sqlite3.connect(str(zotero_db_path))
    try:
        collection_tree = _build_collection_tree(db)
        item_collections = _build_item_collections(db, collection_tree)
        item_ids = _build_item_identifiers(db)
    finally:
        db.close()

    updated = 0
    for iid, cols in item_collections.items():
        idents = item_ids.get(iid, {})
        doi = idents.get("doi", "").lower()
        url = idents.get("url", "")

        paper = None
        if doi and doi in doi_index:
            paper = doi_index[doi]
        elif url and url in url_index:
            paper = url_index[url]

        if paper is None:
            continue

        folder_tags = {f"folder:{c}" for c in cols}
        existing_folders = {t for t in paper.tags if t.startswith("folder:")}

        if folder_tags != existing_folders:
            new_tags = [t for t in paper.tags if not t.startswith("folder:")]
            new_tags.extend(sorted(folder_tags))
            paper.tags = new_tags
            if not dry_run:
                save_paper(paper, lib)
            updated += 1

    unmatched = sum(
        1 for iid in item_collections
        if iid in item_ids and not _find_paper(item_ids[iid], doi_index, url_index)
    )

    return updated, unmatched


def _find_paper(
    idents: dict[str, str],
    doi_index: dict[str, Paper],
    url_index: dict[str, Paper],
) -> Paper | None:
    doi = idents.get("doi", "").lower()
    url = idents.get("url", "")
    if doi and doi in doi_index:
        return doi_index[doi]
    if url and url in url_index:
        return url_index[url]
    return None
