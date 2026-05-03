from __future__ import annotations

import json
import os
from pathlib import Path

from .models import Paper

_PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_LIBRARY = _PACKAGE_ROOT / "library"


def get_library_dir(override: str | Path | None = None) -> Path:
    if override:
        return Path(override).resolve()
    env = os.environ.get("LITMAN_LIBRARY")
    if env:
        return Path(env).resolve()
    return _DEFAULT_LIBRARY


def _papers_dir(library_dir: Path) -> Path:
    d = library_dir / "papers"
    d.mkdir(parents=True, exist_ok=True)
    return d



def save_paper(paper: Paper, library_dir: Path | None = None) -> Path:
    lib = get_library_dir(library_dir)
    path = _papers_dir(lib) / f"{paper.id}.json"
    data = json.dumps(
        paper.model_dump(), indent=2, ensure_ascii=False, sort_keys=True
    )
    path.write_text(data + "\n", encoding="utf-8")
    return path


def load_paper(paper_id: str, library_dir: Path | None = None) -> Paper:
    lib = get_library_dir(library_dir)
    path = _papers_dir(lib) / f"{paper_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return Paper.model_validate(data)


def load_all_papers(library_dir: Path | None = None) -> list[Paper]:
    lib = get_library_dir(library_dir)
    papers_dir = _papers_dir(lib)
    papers = []
    for path in sorted(papers_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        papers.append(Paper.model_validate(data))
    return papers


def delete_paper(paper_id: str, library_dir: Path | None = None) -> None:
    lib = get_library_dir(library_dir)
    json_path = _papers_dir(lib) / f"{paper_id}.json"
    if json_path.exists():
        json_path.unlink()


def find_duplicate(
    doi: str | None, url: str, library_dir: Path | None = None
) -> Paper | None:
    for paper in load_all_papers(library_dir):
        if doi and paper.doi and paper.doi.lower() == doi.lower():
            return paper
        if paper.url == url:
            return paper
    return None



def rename_folder(old_path: str, new_path: str, library_dir: Path | None = None) -> int:
    old_tag = f"folder:{old_path}"
    new_tag = f"folder:{new_path}"
    old_prefix = f"folder:{old_path}/"
    new_prefix = f"folder:{new_path}/"
    count = 0
    for paper in load_all_papers(library_dir):
        changed = False
        new_tags = []
        for t in paper.tags:
            if t == old_tag:
                new_tags.append(new_tag)
                changed = True
            elif t.startswith(old_prefix):
                new_tags.append(new_prefix + t[len(old_prefix):])
                changed = True
            else:
                new_tags.append(t)
        if changed:
            paper.tags = new_tags
            save_paper(paper, library_dir)
            count += 1
    return count


def delete_folder(folder_path: str, library_dir: Path | None = None) -> int:
    tag = f"folder:{folder_path}"
    prefix = f"folder:{folder_path}/"
    count = 0
    for paper in load_all_papers(library_dir):
        old_len = len(paper.tags)
        paper.tags = [t for t in paper.tags if t != tag and not t.startswith(prefix)]
        if len(paper.tags) != old_len:
            save_paper(paper, library_dir)
            count += 1
    return count


def add_folder_to_papers(
    paper_ids: list[str], folder_path: str, library_dir: Path | None = None
) -> int:
    tag = f"folder:{folder_path}"
    count = 0
    for pid in paper_ids:
        try:
            paper = load_paper(pid, library_dir)
        except FileNotFoundError:
            continue
        if tag not in paper.tags:
            paper.tags.append(tag)
            save_paper(paper, library_dir)
            count += 1
    return count


# ── Member / Config ──────────────────────────────────────────────────────

_CONFIG_FILE = "config.json"
_PREFIX = "PreCAM"


def _config_path(library_dir: Path | None = None) -> Path:
    return get_library_dir(library_dir) / _CONFIG_FILE


def load_config(library_dir: Path | None = None) -> dict:
    path = _config_path(library_dir)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"members": [], "prefix": _PREFIX}


def save_config(config: dict, library_dir: Path | None = None) -> None:
    path = _config_path(library_dir)
    path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def get_members(library_dir: Path | None = None) -> list[str]:
    return load_config(library_dir).get("members", [])


def get_prefix(library_dir: Path | None = None) -> str:
    return load_config(library_dir).get("prefix", _PREFIX)


def member_root(member: str, library_dir: Path | None = None) -> str:
    prefix = get_prefix(library_dir)
    return f"{prefix}-{member}"


def add_member(name: str, library_dir: Path | None = None) -> None:
    config = load_config(library_dir)
    if name not in config.get("members", []):
        config.setdefault("members", []).append(name)
        save_config(config, library_dir)


def remove_member(name: str, library_dir: Path | None = None) -> None:
    config = load_config(library_dir)
    members = config.get("members", [])
    if name in members:
        members.remove(name)
        save_config(config, library_dir)


# ── Custom Citation Styles ────────────────────────────────────────────────

def get_custom_styles(library_dir: Path | None = None) -> list[dict]:
    return load_config(library_dir).get("custom_styles", [])


def save_custom_style(style: dict, library_dir: Path | None = None) -> None:
    config = load_config(library_dir)
    styles = config.get("custom_styles", [])
    styles = [s for s in styles if s["name"] != style["name"]]
    styles.append(style)
    config["custom_styles"] = styles
    save_config(config, library_dir)


def delete_custom_style(name: str, library_dir: Path | None = None) -> None:
    config = load_config(library_dir)
    styles = config.get("custom_styles", [])
    config["custom_styles"] = [s for s in styles if s["name"] != name]
    save_config(config, library_dir)
