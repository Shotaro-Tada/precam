from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from litman.bibtex import generate_bibtex, export_library_bib
from litman.importer import bibtex_to_papers
from litman.citation import (
    AUTHOR_FORMATS,
    STYLES,
    format_citation,
    format_citation_html,
    render_custom_style,
    render_custom_style_html,
)
from litman.fetchers import fetch_metadata
from litman.fetchers.crossref import fetch_by_doi
from litman.models import Paper
from litman.search import filter_papers, search_papers
from litman.store import (
    add_member,
    delete_custom_style,
    delete_folder,
    delete_paper,
    find_duplicate,
    get_custom_styles,
    get_library_dir,
    get_members,
    load_all_papers,
    load_config,
    member_root,
    remove_member,
    save_config,
    save_custom_style,
    save_paper,
)

st.set_page_config(page_title="litman", page_icon="📚", layout="wide")

st.markdown(
    """<style>
    [data-testid="stToolbar"] {display: none !important;}
    footer {visibility: hidden;}
    @keyframes litman-blink {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.3; }
    }
    .fix-doi-blink button {
        animation: litman-blink 1.5s ease-in-out infinite;
    }
    .fix-doi-blink button:hover {
        animation: none;
        opacity: 1;
    }
    </style>""",
    unsafe_allow_html=True,
)

LIB = get_library_dir()


# ── Clipboard helper (Windows: rich text, fallback: plain text) ─────────

def _copy_to_clipboard(html: str, plain: str) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = wintypes.BOOL

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    cf_html_fmt = user32.RegisterClipboardFormatW("HTML Format")

    header_tmpl = (
        "Version:0.9\r\n"
        "StartHTML:{:010d}\r\n"
        "EndHTML:{:010d}\r\n"
        "StartFragment:{:010d}\r\n"
        "EndFragment:{:010d}\r\n"
    )
    prefix = "<html><body>\r\n<!--StartFragment-->"
    suffix = "<!--EndFragment-->\r\n</body></html>"

    dummy = header_tmpl.format(0, 0, 0, 0)
    start_html = len(dummy.encode("utf-8"))
    start_frag = start_html + len(prefix.encode("utf-8"))
    end_frag = start_frag + len(html.encode("utf-8"))
    end_html = end_frag + len(suffix.encode("utf-8"))

    cf_data = (header_tmpl.format(start_html, end_html, start_frag, end_frag)
               + prefix + html + suffix)
    cf_bytes = cf_data.encode("utf-8") + b"\x00"

    plain_enc = (plain + "\x00").encode("utf-16-le")

    user32.OpenClipboard(None)
    user32.EmptyClipboard()

    h_plain = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(plain_enc))
    p_plain = kernel32.GlobalLock(h_plain)
    ctypes.memmove(p_plain, plain_enc, len(plain_enc))
    kernel32.GlobalUnlock(h_plain)
    user32.SetClipboardData(CF_UNICODETEXT, h_plain)

    h_html = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(cf_bytes))
    p_html = kernel32.GlobalLock(h_html)
    ctypes.memmove(p_html, cf_bytes, len(cf_bytes))
    kernel32.GlobalUnlock(h_html)
    user32.SetClipboardData(cf_html_fmt, h_html)

    user32.CloseClipboard()


# ── Data loading ─────────────────────────────────────────────────────────

@st.cache_data(ttl=5)
def load_library() -> list[Paper]:
    return load_all_papers(LIB)


def _collect_folders(papers: list[Paper]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for p in papers:
        for t in p.tags:
            if t.startswith("folder:"):
                counts[t[7:]] = counts.get(t[7:], 0) + 1
    return counts


def _build_folder_options(root: str, folder_counts: dict[str, int]) -> list[tuple[str, str]]:
    """Build (value, display_label) pairs for a member's folder tree."""
    options: list[tuple[str, str]] = [("ALL", "All folders")]

    def _recurse(prefix: str, depth: int):
        needle = prefix + "/"
        children = []
        for fp in sorted(folder_counts.keys(), reverse=True):
            if fp.startswith(needle):
                remainder = fp[len(needle):]
                if "/" not in remainder:
                    children.append((fp, remainder))
        for fp, name in children:
            indent = "　" * depth + "└ " if depth > 0 else ""
            cnt = folder_counts.get(fp, 0)
            options.append((fp, f"{indent}{name} ({cnt})"))
            _recurse(fp, depth + 1)

    root_cnt = folder_counts.get(root, 0)
    options.append((root, f"{root} ({root_cnt})"))
    _recurse(root, 1)
    return options


def _descendants_count(prefix: str, folder_counts: dict[str, int]) -> int:
    total = folder_counts.get(prefix, 0)
    for fp, cnt in folder_counts.items():
        if fp.startswith(prefix + "/"):
            total += cnt
    return total


def filter_by_folder(papers: list[Paper], folder_path: str) -> list[Paper]:
    tag_exact = f"folder:{folder_path}"
    tag_prefix = f"folder:{folder_path}/"
    return [
        p for p in papers
        if tag_exact in p.tags or any(t.startswith(tag_prefix) for t in p.tags)
    ]


all_papers = load_library()
folder_counts = _collect_folders(all_papers)
members = get_members(LIB)

all_non_folder_tags = sorted({t for p in all_papers for t in p.tags if not t.startswith("folder:")})
all_journals = sorted({p.journal for p in all_papers if p.journal})
years = [p.year for p in all_papers if p.year]


# ── Sidebar ──────────────────────────────────────────────────────────────

_title_col, _sync_col = st.sidebar.columns([3, 1])
with _title_col:
    st.title("litman")
with _sync_col:
    st.markdown("<br>", unsafe_allow_html=True)
    _sync_btn = st.button("Sync", key="sidebar_sync_btn", help="Pull → Push with shared library")
st.sidebar.caption("Lightweight Literature Manager")

page = st.sidebar.radio("", ["Library", "Add Paper", "Import", "Export", "Sync"], label_visibility="collapsed")

st.sidebar.markdown("---")

# ── Member selector (pulldown) ───────────────────────────────────────────

member_options = ["All Members"] + members
sb_col1, sb_col2 = st.sidebar.columns([4, 1])
with sb_col1:
    selected_member = st.selectbox(
        "Member",
        member_options,
        key="sidebar_member",
    )
with sb_col2:
    st.markdown("<br>", unsafe_allow_html=True)
    add_mem_open = st.button("＋", key="sb_add_mem_btn", help="Add new member")

if add_mem_open:
    st.session_state["show_add_member"] = True

if st.session_state.get("show_add_member"):
    new_name = st.sidebar.text_input("New member name", key="sb_new_member")
    mc1, mc2 = st.sidebar.columns(2)
    if mc1.button("Add", key="sb_confirm_add_mem"):
        if new_name.strip():
            add_member(new_name.strip(), LIB)
            st.session_state.pop("show_add_member", None)
            st.cache_data.clear()
            st.rerun()
    if mc2.button("Cancel", key="sb_cancel_add_mem"):
        st.session_state.pop("show_add_member", None)
        st.rerun()

# ── Folder selector (pulldown) ───────────────────────────────────────────

if selected_member == "All Members":
    # Show all top-level member roots
    folder_opts = [("ALL", f"All Papers ({len(all_papers)})")]
    for mem in members:
        root = member_root(mem, LIB)
        total = _descendants_count(root, folder_counts)
        folder_opts.append((root, f"{root} ({total})"))
else:
    root = member_root(selected_member, LIB)
    folder_opts = _build_folder_options(root, folder_counts)

folder_keys = [k for k, _ in folder_opts]
folder_labels = {k: v for k, v in folder_opts}

selected_folder = st.sidebar.selectbox(
    "Folder",
    folder_keys,
    format_func=lambda k: folder_labels[k],
    key="sidebar_folder",
)

# ── Filters ──────────────────────────────────────────────────────────────

st.sidebar.markdown("---")
search_query = st.sidebar.text_input("Search", placeholder="keyword...")

selected_tags = st.sidebar.multiselect("Tags", all_non_folder_tags) if all_non_folder_tags else []

year_range = None
if years:
    min_y, max_y = min(years), max(years)
    if min_y < max_y:
        year_range = st.sidebar.slider("Year", min_y, max_y, (min_y, max_y))

selected_journal = st.sidebar.selectbox("Journal", ["All"] + all_journals) if all_journals else "All"

# ── Citation Style selector ─────────────────────────────────────────────

custom_styles = get_custom_styles(LIB)
custom_style_names = [s["name"] for s in custom_styles]
all_cite_styles = STYLES + custom_style_names

sidebar_cite_style = st.sidebar.selectbox(
    "Citation Style", all_cite_styles, key="sidebar_cite_style"
)
st.sidebar.caption("Need a different style? Contact the admin.")

# ── Manage (bottom of sidebar) ───────────────────────────────────────────

st.sidebar.markdown("---")
st.sidebar.markdown(f"**{len(all_papers)}** papers · **{len(members)}** members")

with st.sidebar.expander("Manage Folders / Members"):
    tab_f, tab_m = st.tabs(["Folders", "Members"])

    with tab_f:
        new_folder = st.text_input("New folder name", key="mng_new_folder")
        parent_opts = ["(root)"] + sorted(folder_counts.keys())
        parent_choice = st.selectbox("Under", parent_opts, key="mng_folder_parent")
        if st.button("Create", key="mng_create_folder"):
            if new_folder.strip():
                full = new_folder.strip() if parent_choice == "(root)" else f"{parent_choice}/{new_folder.strip()}"
                st.success(f"Created: {full}")
                st.caption("Assign papers to populate.")
            else:
                st.warning("Enter a name.")

        st.markdown("---")
        del_fps = sorted(folder_counts.keys())
        if del_fps:
            del_choice = st.selectbox("Delete folder", del_fps, key="mng_del_folder")
            if st.button("Delete", key="mng_del_folder_btn", type="secondary"):
                st.session_state["confirm_del_folder"] = del_choice

            if st.session_state.get("confirm_del_folder"):
                target = st.session_state["confirm_del_folder"]
                st.warning(f"Remove '{target.split('/')[-1]}' from all papers?")
                c1, c2 = st.columns(2)
                if c1.button("Yes", key="mng_yes_del"):
                    delete_folder(target, LIB)
                    st.session_state.pop("confirm_del_folder", None)
                    st.cache_data.clear()
                    st.rerun()
                if c2.button("No", key="mng_no_del"):
                    st.session_state.pop("confirm_del_folder", None)
                    st.rerun()

    with tab_m:
        st.caption("Current members")
        for m in members:
            st.write(f"• {m}")
        new_m = st.text_input("Add member", key="mng_new_member")
        if st.button("Add", key="mng_add_member"):
            if new_m.strip():
                add_member(new_m.strip(), LIB)
                st.cache_data.clear()
                st.rerun()
        if members:
            rm_m = st.selectbox("Remove member", members, key="mng_rm_member")
            st.caption("Papers are kept.")
            if st.button("Remove", key="mng_rm_member_btn"):
                remove_member(rm_m, LIB)
                st.cache_data.clear()
                st.rerun()


# ── Filtering logic ──────────────────────────────────────────────────────

def get_filtered_papers() -> list[Paper]:
    papers = all_papers
    if selected_folder and selected_folder != "ALL":
        papers = filter_by_folder(papers, selected_folder)
    if search_query:
        papers = search_papers(papers, search_query)
    if selected_tags:
        papers = filter_papers(papers, tags=selected_tags)
    if year_range:
        papers = filter_papers(papers, year_from=year_range[0], year_to=year_range[1])
    if selected_journal and selected_journal != "All":
        papers = filter_papers(papers, journal=selected_journal)
    papers.sort(key=lambda p: p.added_at, reverse=True)
    return papers


# ── Sidebar Sync (Pull → Push) ──────────────────────────────────────────

if _sync_btn:
    import subprocess
    _sync_config = load_config(LIB)
    _sync_repo = _sync_config.get("library_repo", "") or "https://github.com/Shotaro-Tada/precam-litman-library.git"
    if not _sync_repo:
        st.sidebar.error("Set repository URL in Export → Sync Settings first.")
    else:
        _lib_str = str(LIB)
        try:
            # ensure git
            _gi = LIB / ".gitignore"
            if not _gi.exists():
                _gi.write_text(
                    "*.token\n*.key\n.env\n__pycache__/\n"
                    ".DS_Store\nThumbs.db\nlibrary.bib\n",
                    encoding="utf-8",
                )
            if not (LIB / ".git").exists():
                subprocess.run(["git", "init"], cwd=_lib_str, check=True, capture_output=True)
                subprocess.run(["git", "branch", "-M", "main"], cwd=_lib_str, check=True, capture_output=True)
            _r = subprocess.run(["git", "remote", "get-url", "origin"], cwd=_lib_str, capture_output=True, text=True)
            if _r.returncode != 0:
                subprocess.run(["git", "remote", "add", "origin", _sync_repo], cwd=_lib_str, check=True, capture_output=True)
            elif _r.stdout.strip() != _sync_repo:
                subprocess.run(["git", "remote", "set-url", "origin", _sync_repo], cwd=_lib_str, check=True, capture_output=True)

            # commit local
            subprocess.run(["git", "add", "-A"], cwd=_lib_str, check=True, capture_output=True)
            _has = subprocess.run(["git", "rev-parse", "HEAD"], cwd=_lib_str, capture_output=True).returncode == 0
            if _has:
                if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=_lib_str, capture_output=True).returncode != 0:
                    subprocess.run(["git", "commit", "-m", "litman: local snapshot"], cwd=_lib_str, check=True, capture_output=True)
            else:
                subprocess.run(["git", "commit", "-m", "litman: initial library"], cwd=_lib_str, check=True, capture_output=True)
                _has = True

            # pull
            _fetch = subprocess.run(["git", "fetch", "origin", "main"], cwd=_lib_str, capture_output=True, text=True)
            _remote_exists = _fetch.returncode == 0 and subprocess.run(
                ["git", "rev-parse", "--verify", "origin/main"], cwd=_lib_str, capture_output=True,
            ).returncode == 0

            _pull_ok = True
            if _remote_exists:
                _diff = subprocess.run(
                    ["git", "diff", "--name-status", "HEAD", "origin/main"],
                    cwd=_lib_str, capture_output=True, text=True,
                )
                _del_lines = [l for l in _diff.stdout.strip().splitlines() if l.startswith("D")]
                if len(_del_lines) > 10:
                    st.session_state["quick_sync_warn"] = len(_del_lines)
                    _pull_ok = False
                else:
                    _merge = subprocess.run(
                        ["git", "merge", "origin/main", "--allow-unrelated-histories",
                         "-m", "litman: pull from shared library"],
                        cwd=_lib_str, capture_output=True, text=True,
                    )
                    if _merge.returncode != 0:
                        subprocess.run(["git", "merge", "--abort"], cwd=_lib_str, capture_output=True)
                        _merge = subprocess.run(
                            ["git", "merge", "origin/main", "--allow-unrelated-histories",
                             "-X", "theirs", "-m", "litman: pull from shared library"],
                            cwd=_lib_str, capture_output=True, text=True,
                        )
                    if _merge.returncode != 0:
                        st.sidebar.error(f"Merge failed: {_merge.stderr[:120]}")
                        _pull_ok = False

            # push
            if _pull_ok:
                subprocess.run(["git", "add", "-A"], cwd=_lib_str, check=True, capture_output=True)
                if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=_lib_str, capture_output=True).returncode != 0:
                    subprocess.run(["git", "commit", "-m", "litman: sync library"], cwd=_lib_str, check=True, capture_output=True)
                _push = subprocess.run(["git", "push", "-u", "origin", "main"], cwd=_lib_str, capture_output=True, text=True)
                if _push.returncode == 0:
                    st.sidebar.success("Sync complete!")
                    st.cache_data.clear()
                elif "rejected" in _push.stderr:
                    st.sidebar.error("Push rejected — try again.")
                else:
                    st.sidebar.error(f"Push failed: {_push.stderr[:120]}")
        except subprocess.CalledProcessError as e:
            st.sidebar.error(f"Git error: {(e.stderr.decode() if e.stderr else str(e))[:120]}")

if st.session_state.get("quick_sync_warn"):
    _n = st.session_state["quick_sync_warn"]
    st.sidebar.warning(f"{_n} files will be deleted. Use Export → Sync Settings for detailed Pull/Push.")
    if st.sidebar.button("Dismiss", key="sync_warn_dismiss"):
        st.session_state.pop("quick_sync_warn", None)
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════
# ── Library Page ─────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════

if page == "Library":
    papers = get_filtered_papers()

    if selected_folder and selected_folder != "ALL":
        display_name = selected_folder.split("/")[-1]
        st.header(f"{display_name} ({len(papers)})")
    else:
        st.header(f"Library ({len(papers)} papers)")

    if not papers:
        st.info("No papers found. Add some papers to get started!")
    else:
        if "selected_paper" not in st.session_state:
            st.session_state.selected_paper = None

        col_list, col_detail = st.columns([2, 3])

        with col_list:
            with st.container(height=700):
                for p in papers:
                    first_author = p.authors[0].family if p.authors else "?"
                    if len(p.authors) > 1:
                        first_author += " et al."
                    label = f"**{p.title[:80]}**  \n{first_author} · {p.year or '?'} · {p.journal or ''}"

                    is_sel = st.session_state.get("selected_paper") == p.id
                    if st.button(
                        label,
                        key=f"paper_{p.id}",
                        use_container_width=True,
                        type="primary" if is_sel else "secondary",
                    ):
                        st.session_state.selected_paper = p.id
                        st.rerun()

        with col_detail:
          with st.container(height=700):
            sel_id = st.session_state.selected_paper
            if sel_id:
                try:
                    paper = next(p for p in papers if p.id == sel_id)
                except StopIteration:
                    paper = None

                if paper:
                    st.subheader(paper.title)
                    st.markdown(
                        f"**Authors:** {', '.join(a.full_name() for a in paper.authors)}"
                    )

                    _j_display = paper.journal or "N/A"
                    if paper.journal_abbrev and paper.journal_abbrev != paper.journal:
                        _j_display += f" ({paper.journal_abbrev})"
                    st.markdown(
                        f"**Year:** {paper.year or 'N/A'} &nbsp;&nbsp; "
                        f"**Journal:** {_j_display}  \n"
                        f"**DOI:** {paper.doi or 'N/A'}"
                    )

                    folders = [t[7:] for t in paper.tags if t.startswith("folder:")]
                    if folders:
                        st.markdown("**Folders:** " + "  ".join(f"`{f}`" for f in folders))

                    if paper.abstract:
                        with st.expander("Abstract", expanded=True):
                            st.write(paper.abstract)

                    # ── Fix from DOI ──────────────────────────────
                    _missing = (
                        not paper.year
                        or not paper.journal
                        or not paper.journal_abbrev
                        or not paper.authors
                        or not paper.abstract
                        or not paper.volume
                        or not paper.issue
                        or not paper.pages
                        or not paper.publisher
                        or paper.title == "Untitled"
                    )
                    if paper.doi and _missing:
                      with st.container():
                        st.markdown('<div class="fix-doi-blink">', unsafe_allow_html=True)
                        if st.button("Fix information from DOI", key=f"fix_{paper.id}"):
                            with st.spinner("Fetching from CrossRef..."):
                                try:
                                    fresh = fetch_by_doi(paper.doi, paper.url or "")
                                    if not paper.year and fresh.year:
                                        paper.year = fresh.year
                                    if not paper.authors and fresh.authors:
                                        paper.authors = fresh.authors
                                    if not paper.journal and fresh.journal:
                                        paper.journal = fresh.journal
                                    if not paper.journal_abbrev and fresh.journal_abbrev:
                                        paper.journal_abbrev = fresh.journal_abbrev
                                    if not paper.abstract and fresh.abstract:
                                        paper.abstract = fresh.abstract
                                    if not paper.volume and fresh.volume:
                                        paper.volume = fresh.volume
                                    if not paper.issue and fresh.issue:
                                        paper.issue = fresh.issue
                                    if not paper.pages and fresh.pages:
                                        paper.pages = fresh.pages
                                    if not paper.publisher and fresh.publisher:
                                        paper.publisher = fresh.publisher
                                    if paper.title == "Untitled" and fresh.title != "Untitled":
                                        paper.title = fresh.title
                                    paper.updated_at = datetime.now().isoformat(timespec="seconds")
                                    save_paper(paper, LIB)
                                    st.cache_data.clear()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed: {e}")
                        st.markdown('</div>', unsafe_allow_html=True)

                    if paper.url:
                        st.markdown(
                            f'<a href="{paper.url}" target="_blank" rel="noopener noreferrer">Open original URL</a>',
                            unsafe_allow_html=True,
                        )

                    # ── Citation ───────────────────────────────────────
                    st.markdown(f"**Refer this paper** — {sidebar_cite_style}")
                    _is_custom = sidebar_cite_style in custom_style_names
                    _custom_def = next((s for s in custom_styles if s["name"] == sidebar_cite_style), None) if _is_custom else None

                    use_abbrev = st.checkbox(
                        "Journal abbreviation",
                        value=True,
                        key=f"abbrev_{paper.id}",
                        disabled=not paper.journal_abbrev,
                        help=paper.journal_abbrev or "Run 'Fix information from DOI' to fetch abbreviation",
                    )
                    cite_col1, cite_col2 = st.columns(2)
                    _copied = False
                    _abbr = use_abbrev and bool(paper.journal_abbrev)
                    with cite_col1:
                        if st.button("Copy (with DOI)", key=f"ref_doi_{paper.id}", use_container_width=True):
                            if _is_custom and _custom_def:
                                cite_html = render_custom_style_html(paper, _custom_def, with_doi=True, abbrev=_abbr)
                                cite_plain = render_custom_style(paper, _custom_def, with_doi=True, abbrev=_abbr)
                            else:
                                cite_html = format_citation_html(paper, sidebar_cite_style, with_doi=True, abbrev=_abbr)
                                cite_plain = format_citation(paper, sidebar_cite_style, with_doi=True, abbrev=_abbr)
                            _copy_to_clipboard(cite_html, cite_plain)
                            st.session_state[f"cite_result_{paper.id}"] = cite_html
                            _copied = True
                    with cite_col2:
                        if st.button("Copy (w/o DOI)", key=f"ref_nodoi_{paper.id}", use_container_width=True):
                            if _is_custom and _custom_def:
                                cite_html = render_custom_style_html(paper, _custom_def, with_doi=False, abbrev=_abbr)
                                cite_plain = render_custom_style(paper, _custom_def, with_doi=False, abbrev=_abbr)
                            else:
                                cite_html = format_citation_html(paper, sidebar_cite_style, with_doi=False, abbrev=_abbr)
                                cite_plain = format_citation(paper, sidebar_cite_style, with_doi=False, abbrev=_abbr)
                            _copy_to_clipboard(cite_html, cite_plain)
                            st.session_state[f"cite_result_{paper.id}"] = cite_html
                            _copied = True

                    if _copied:
                        st.success("Copied to clipboard!")
                    if st.session_state.get(f"cite_result_{paper.id}"):
                        st.markdown(
                            f'<div style="background:#1e1e1e;padding:12px;border-radius:6px;'
                            f'margin:8px 0;font-size:14px;line-height:1.6;">'
                            f'{st.session_state[f"cite_result_{paper.id}"]}</div>',
                            unsafe_allow_html=True,
                        )

                    # ── Edit ──────────────────────────────────────────
                    st.markdown("---")
                    user_tags = [t for t in paper.tags if not t.startswith("folder:")]
                    new_tags = st.text_input(
                        "Tags (comma-separated)",
                        value=", ".join(user_tags),
                        key=f"tags_{paper.id}",
                    )
                    new_notes = st.text_area(
                        "Notes", value=paper.notes, key=f"notes_{paper.id}"
                    )

                    btn_cols = st.columns(3)
                    if btn_cols[0].button("Save changes", key=f"save_{paper.id}"):
                        folder_tags = [t for t in paper.tags if t.startswith("folder:")]
                        paper.tags = [t.strip() for t in new_tags.split(",") if t.strip()] + folder_tags
                        paper.notes = new_notes
                        paper.updated_at = datetime.now().isoformat(timespec="seconds")
                        save_paper(paper, LIB)
                        st.cache_data.clear()
                        st.success("Saved!")
                        st.rerun()

                    if btn_cols[1].button("BibTeX", key=f"bib_{paper.id}"):
                        st.code(generate_bibtex(paper), language="bibtex")

                    if btn_cols[2].button("Delete", key=f"del_{paper.id}", type="secondary"):
                        st.session_state[f"confirm_delete_{paper.id}"] = True

                    if st.session_state.get(f"confirm_delete_{paper.id}"):
                        st.warning("Are you sure?")
                        c1, c2 = st.columns(2)
                        if c1.button("Yes, delete", key=f"yes_del_{paper.id}", type="primary"):
                            delete_paper(paper.id, LIB)
                            st.session_state.selected_paper = None
                            st.session_state.pop(f"confirm_delete_{paper.id}", None)
                            st.cache_data.clear()
                            st.rerun()
                        if c2.button("Cancel", key=f"cancel_del_{paper.id}"):
                            st.session_state.pop(f"confirm_delete_{paper.id}", None)
                            st.rerun()
            else:
                st.info("Select a paper from the list to view details.")


# ══════════════════════════════════════════════════════════════════════════
# ── Add Paper Page ───────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════

elif page == "Add Paper":
    st.header("Add Paper")

    url = st.text_input("Paper URL (DOI link, arXiv, or publisher page)")

    # Member selector with inline add
    add_col1, add_col2 = st.columns([4, 1])
    with add_col1:
        member_choice = st.selectbox("Member", members, key="add_member") if members else None
    with add_col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("＋", key="add_page_new_mem", help="Add new member"):
            st.session_state["show_add_member_addpage"] = True

    if st.session_state.get("show_add_member_addpage"):
        nm = st.text_input("New member name", key="add_page_mem_name")
        nc1, nc2 = st.columns(2)
        if nc1.button("Add", key="add_page_confirm_mem"):
            if nm.strip():
                add_member(nm.strip(), LIB)
                st.session_state.pop("show_add_member_addpage", None)
                st.cache_data.clear()
                st.rerun()
        if nc2.button("Cancel", key="add_page_cancel_mem"):
            st.session_state.pop("show_add_member_addpage", None)
            st.rerun()

    tags_input = st.text_input("Tags (comma-separated)", placeholder="catalyst, DFT, review")

    # Folder selector filtered by member
    folder_opts_add = ["None"]
    if member_choice:
        root = member_root(member_choice, LIB)
        folder_opts_add.append(root)
        for fp in sorted(folder_counts.keys(), reverse=True):
            if fp.startswith(root + "/"):
                folder_opts_add.append(fp)

    def _add_folder_label(fp: str) -> str:
        if fp == "None":
            return "None"
        parts = fp.split("/")
        if len(parts) <= 1:
            return fp
        indent = "　" * (len(parts) - 1) + "└ "
        return f"{indent}{parts[-1]}"

    assign_folder = st.selectbox(
        "Assign to folder",
        folder_opts_add,
        format_func=_add_folder_label,
        key="add_folder",
    )

    if st.button("Add", type="primary", disabled=not url):
        with st.spinner("Fetching metadata..."):
            try:
                paper = fetch_metadata(url)
            except Exception as e:
                st.error(f"Failed to fetch metadata: {e}")
                st.stop()

            dup = find_duplicate(paper.doi, url, LIB)

            if tags_input:
                paper.tags = [t.strip() for t in tags_input.split(",") if t.strip()]

            if assign_folder and assign_folder != "None":
                paper.tags.append(f"folder:{assign_folder}")

            save_paper(paper, LIB)
            st.cache_data.clear()

        st.success(f"Added: **{paper.title}**")
        if dup:
            st.info(f"Note: duplicate exists — [{dup.id}] {dup.title[:60]}")
        st.markdown(f"- Authors: {', '.join(a.full_name() for a in paper.authors)}")
        st.markdown(f"- Year: {paper.year}")
        st.markdown(f"- DOI: {paper.doi or 'N/A'}")
        st.markdown(f"- ID: `{paper.id}`")


# ══════════════════════════════════════════════════════════════════════════
# ── Import Page ──────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════

elif page == "Import":
    st.header("Import")

    uploaded = st.file_uploader("Upload BibTeX file (.bib)", type=["bib"])

    imp_member = st.selectbox("Member", members, key="imp_member") if members else None

    # Folder selector filtered by member
    imp_folder_opts = ["None"]
    if imp_member:
        imp_root = member_root(imp_member, LIB)
        imp_folder_opts.append(imp_root)
        for fp in sorted(folder_counts.keys(), reverse=True):
            if fp.startswith(imp_root + "/"):
                imp_folder_opts.append(fp)

    def _imp_folder_label(fp: str) -> str:
        if fp == "None":
            return "None"
        parts = fp.split("/")
        if len(parts) <= 1:
            return fp
        indent = "　" * (len(parts) - 1) + "└ "
        return f"{indent}{parts[-1]}"

    imp_folder = st.selectbox(
        "Assign to folder",
        imp_folder_opts,
        format_func=_imp_folder_label,
        key="imp_folder",
    )

    with st.expander("How to include folder structure"):
        st.markdown("""
**Zotero**
1. File → Export Library → Format: **BibTeX** → Check **Export Notes**
2. Zotero does **not** embed folder (collection) paths in BibTeX.
   To import folder structure, use the CLI command:
   ```
   litman zotero-sync <path/to/zotero.sqlite>
   ```
   This reads Zotero's SQLite database directly and applies `folder:` tags.

**Mendeley**
1. File → Export → BibTeX (`.bib`)
2. Mendeley stores folders as the `keywords` field. litman converts these to tags automatically.

**EndNote**
1. File → Export → Output Style: **BibTeX Export**
2. Folders (groups) are **not** included. Assign a folder above, or tag papers manually after import.

**Other apps**
- If your app exports `keywords` or `groups` in BibTeX, litman imports them as tags.
- Otherwise, select a folder above to assign all imported papers to a specific folder.
""")

    dry_run = st.checkbox("Dry run (preview only)")

    if st.button("Import", type="primary", disabled=uploaded is None):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".bib", delete=False, mode="wb") as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = Path(tmp.name)

        with st.spinner("Parsing BibTeX..."):
            papers = bibtex_to_papers(tmp_path)
        tmp_path.unlink(missing_ok=True)

        st.write(f"Found **{len(papers)}** entries.")

        added = 0
        skipped = 0
        imported_list = []
        for paper in papers:
            dup = find_duplicate(paper.doi, paper.url, LIB)
            if dup:
                skipped += 1
                continue
            if imp_folder and imp_folder != "None":
                paper.tags.append(f"folder:{imp_folder}")
            if not dry_run:
                save_paper(paper, LIB)
            imported_list.append(paper)
            added += 1

        if dry_run:
            st.info(f"Dry run: **{added}** would be added, **{skipped}** duplicates skipped.")
            if imported_list:
                with st.expander("Preview", expanded=True):
                    for p in imported_list[:50]:
                        st.write(f"- {p.bibtex_key}: {p.title[:70]}")
                    if len(imported_list) > 50:
                        st.caption(f"... and {len(imported_list) - 50} more")
        else:
            st.cache_data.clear()
            st.success(f"Imported **{added}** papers, skipped **{skipped}** duplicates.")


# ══════════════════════════════════════════════════════════════════════════
# ── Export Page ───────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════

elif page == "Export":
    st.header("Export")

    exp_member = st.selectbox(
        "Member",
        ["All Members"] + members,
        key="exp_member",
    )

    # Folder selector linked to member
    if exp_member != "All Members":
        exp_root = member_root(exp_member, LIB)
        exp_folder_opts = _build_folder_options(exp_root, folder_counts)
    else:
        exp_folder_opts = [("ALL", f"All Papers ({len(all_papers)})")]
        for mem in members:
            r = member_root(mem, LIB)
            total = _descendants_count(r, folder_counts)
            exp_folder_opts.append((r, f"{r} ({total})"))

    exp_folder_keys = [k for k, _ in exp_folder_opts]
    exp_folder_labels = {k: v for k, v in exp_folder_opts}

    exp_folder = st.selectbox(
        "Folder",
        exp_folder_keys,
        format_func=lambda k: exp_folder_labels[k],
        key="exp_folder",
    )

    # Filter papers by selection
    if exp_folder and exp_folder != "ALL":
        exp_papers = filter_by_folder(all_papers, exp_folder)
    elif exp_member != "All Members":
        exp_root = member_root(exp_member, LIB)
        exp_papers = filter_by_folder(all_papers, exp_root)
    else:
        exp_papers = all_papers

    st.write(f"**{len(exp_papers)}** papers selected for export")

    if st.button("Generate BibTeX", type="primary"):
        if not exp_papers:
            st.warning("No papers to export.")
        else:
            out = LIB / "library.bib"
            with st.spinner("Generating BibTeX..."):
                export_library_bib(exp_papers, out)
            bib_text = out.read_text(encoding="utf-8")
            st.download_button("Download .bib", bib_text, file_name="library.bib", mime="application/x-bibtex")
            with st.expander("Preview"):
                st.code(bib_text, language="bibtex")

    # ── Library Stats ─────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Library Stats")
    if all_papers:
        stat_cols = st.columns(4)
        stat_cols[0].metric("Total Papers", len(all_papers))
        stat_cols[1].metric("With DOI", sum(1 for p in all_papers if p.doi))
        stat_cols[2].metric("Members", len(members))
        stat_cols[3].metric("Folders", len(folder_counts))

        if years:
            import pandas as pd
            year_counts = pd.Series(years).value_counts().sort_index()
            st.bar_chart(year_counts, x_label="Year", y_label="Papers")


# ══════════════════════════════════════════════════════════════════════════
# ── Sync Page ────────────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════════

elif page == "Sync":
    st.header("Sync")

    _DEFAULT_REPO = "https://github.com/Shotaro-Tada/precam-litman-library.git"

    config = load_config(LIB)
    library_repo = config.get("library_repo", "") or _DEFAULT_REPO

    sync_repo = st.text_input(
        "Shared library repository",
        value=library_repo,
        key="sync_repo_url",
    )
    st.caption("Change this URL to build a library on your own GitHub.")

    if sync_repo != library_repo:
        if st.button("Save", key="sync_save"):
            config = load_config(LIB)
            config["library_repo"] = sync_repo
            save_config(config, LIB)
            st.success("Saved!")
            st.rerun()

    if library_repo:
        import subprocess
        lib_str = str(LIB)

        def _init_lib_git():
            gi = LIB / ".gitignore"
            if not gi.exists():
                gi.write_text(
                    "*.token\n*.key\n.env\n__pycache__/\n"
                    ".DS_Store\nThumbs.db\nlibrary.bib\n",
                    encoding="utf-8",
                )
            if not (LIB / ".git").exists():
                subprocess.run(["git", "init"], cwd=lib_str, check=True, capture_output=True)
                subprocess.run(["git", "branch", "-M", "main"], cwd=lib_str, check=True, capture_output=True)
            r = subprocess.run(["git", "remote", "get-url", "origin"], cwd=lib_str, capture_output=True, text=True)
            if r.returncode != 0:
                subprocess.run(["git", "remote", "add", "origin", library_repo], cwd=lib_str, check=True, capture_output=True)
            elif r.stdout.strip() != library_repo:
                subprocess.run(["git", "remote", "set-url", "origin", library_repo], cwd=lib_str, check=True, capture_output=True)

        def _has_head():
            return subprocess.run(["git", "rev-parse", "HEAD"], cwd=lib_str, capture_output=True).returncode == 0

        def _commit_local(msg="litman: local snapshot"):
            subprocess.run(["git", "add", "-A"], cwd=lib_str, check=True, capture_output=True)
            if _has_head():
                if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=lib_str, capture_output=True).returncode != 0:
                    subprocess.run(["git", "commit", "-m", msg], cwd=lib_str, check=True, capture_output=True)
            else:
                subprocess.run(["git", "commit", "-m", msg], cwd=lib_str, check=True, capture_output=True)

        _DEL_THRESHOLD = 10

        st.markdown("---")
        sc1, sc2 = st.columns(2)
        with sc1:
            pull_btn = st.button("Pull from GitHub", key="sync_pull", use_container_width=True, type="primary")
        with sc2:
            push_btn = st.button("Push to GitHub", key="sync_push", use_container_width=True, type="primary")

        # ── Pull ─────────────────────────────────────────
        if pull_btn:
            try:
                _init_lib_git()
                _commit_local("litman: snapshot before pull")
                fetch_r = subprocess.run(["git", "fetch", "origin", "main"], cwd=lib_str, capture_output=True, text=True)
                if fetch_r.returncode != 0:
                    st.error(f"Fetch failed: {fetch_r.stderr}")
                elif subprocess.run(["git", "rev-parse", "--verify", "origin/main"], cwd=lib_str, capture_output=True).returncode != 0:
                    st.info("Remote is empty. Nothing to pull.")
                else:
                    diff_r = subprocess.run(
                        ["git", "diff", "--name-status", "HEAD", "origin/main"],
                        cwd=lib_str, capture_output=True, text=True,
                    )
                    changes = [l for l in diff_r.stdout.strip().splitlines() if l]
                    deletions = [l for l in changes if l.startswith("D")]
                    if len(deletions) > _DEL_THRESHOLD:
                        st.session_state["sync_pull_warn"] = len(deletions)
                    else:
                        merge_r = subprocess.run(
                            ["git", "merge", "origin/main", "--allow-unrelated-histories",
                             "-m", "litman: pull from shared library"],
                            cwd=lib_str, capture_output=True, text=True,
                        )
                        if merge_r.returncode == 0:
                            st.cache_data.clear()
                            st.success(f"Pull complete! ({len(changes)} file changes)")
                        else:
                            subprocess.run(["git", "merge", "--abort"], cwd=lib_str, capture_output=True)
                            merge_r2 = subprocess.run(
                                ["git", "merge", "origin/main", "--allow-unrelated-histories",
                                 "-X", "theirs", "-m", "litman: pull from shared library"],
                                cwd=lib_str, capture_output=True, text=True,
                            )
                            if merge_r2.returncode == 0:
                                st.cache_data.clear()
                                st.success(f"Pull complete! ({len(changes)} file changes)")
                            else:
                                st.error(f"Merge failed: {merge_r2.stderr}")
            except subprocess.CalledProcessError as e:
                st.error(f"Git error: {e.stderr.decode() if e.stderr else e}")

        if st.session_state.get("sync_pull_warn"):
            n = st.session_state["sync_pull_warn"]
            st.warning(f"{n} files will be removed from your local library. Proceed?")
            pc1, pc2 = st.columns(2)
            if pc1.button("Yes, pull", key="sync_pull_yes", type="primary"):
                try:
                    merge_r = subprocess.run(
                        ["git", "merge", "origin/main", "--allow-unrelated-histories",
                         "-m", "litman: pull from shared library"],
                        cwd=lib_str, capture_output=True, text=True,
                    )
                    st.session_state.pop("sync_pull_warn", None)
                    if merge_r.returncode == 0:
                        st.cache_data.clear()
                        st.success("Pull complete!")
                    else:
                        subprocess.run(["git", "merge", "--abort"], cwd=lib_str, capture_output=True)
                        merge_r2 = subprocess.run(
                            ["git", "merge", "origin/main", "--allow-unrelated-histories",
                             "-X", "theirs", "-m", "litman: pull from shared library"],
                            cwd=lib_str, capture_output=True, text=True,
                        )
                        if merge_r2.returncode == 0:
                            st.cache_data.clear()
                            st.success("Pull complete!")
                        else:
                            st.error(f"Merge failed: {merge_r2.stderr}")
                    st.rerun()
                except subprocess.CalledProcessError as e:
                    st.error(f"Git error: {e.stderr.decode() if e.stderr else e}")
            if pc2.button("Cancel", key="sync_pull_no"):
                st.session_state.pop("sync_pull_warn", None)
                st.rerun()

        # ── Push ─────────────────────────────────────────
        if push_btn:
            try:
                _init_lib_git()
                subprocess.run(["git", "add", "-A"], cwd=lib_str, check=True, capture_output=True)
                has_head = _has_head()
                no_changes = has_head and subprocess.run(
                    ["git", "diff", "--cached", "--quiet"], cwd=lib_str, capture_output=True,
                ).returncode == 0
                if no_changes:
                    st.info("No local changes to push.")
                else:
                    diff_r = subprocess.run(
                        ["git", "diff", "--cached", "--name-status"],
                        cwd=lib_str, capture_output=True, text=True,
                    )
                    changes = [l for l in diff_r.stdout.strip().splitlines() if l]
                    deletions = [l for l in changes if l.startswith("D")]
                    if len(deletions) > _DEL_THRESHOLD:
                        st.session_state["sync_push_warn"] = len(deletions)
                    else:
                        subprocess.run(
                            ["git", "commit", "-m", "litman: sync library"],
                            cwd=lib_str, check=True, capture_output=True,
                        )
                        push_r = subprocess.run(
                            ["git", "push", "-u", "origin", "main"],
                            cwd=lib_str, capture_output=True, text=True,
                        )
                        if push_r.returncode == 0:
                            st.success(f"Pushed! ({len(changes)} file changes)")
                        elif "rejected" in push_r.stderr:
                            st.error("Push rejected — pull first to sync with remote.")
                        else:
                            st.error(f"Push failed: {push_r.stderr}")
            except subprocess.CalledProcessError as e:
                st.error(f"Git error: {e.stderr.decode() if e.stderr else e}")

        if st.session_state.get("sync_push_warn"):
            n = st.session_state["sync_push_warn"]
            st.warning(f"{n} files will be deleted from the shared library. Proceed?")
            pc1, pc2 = st.columns(2)
            if pc1.button("Yes, push", key="sync_push_yes", type="primary"):
                try:
                    subprocess.run(
                        ["git", "commit", "-m", "litman: sync library"],
                        cwd=lib_str, check=True, capture_output=True,
                    )
                    push_r = subprocess.run(
                        ["git", "push", "-u", "origin", "main"],
                        cwd=lib_str, capture_output=True, text=True,
                    )
                    st.session_state.pop("sync_push_warn", None)
                    if push_r.returncode == 0:
                        st.success("Pushed!")
                    else:
                        st.error(f"Push failed: {push_r.stderr}")
                    st.rerun()
                except subprocess.CalledProcessError as e:
                    st.error(f"Git error: {e.stderr.decode() if e.stderr else e}")
            if pc2.button("Cancel", key="sync_push_no"):
                subprocess.run(["git", "reset", "HEAD"], cwd=lib_str, capture_output=True)
                st.session_state.pop("sync_push_warn", None)
                st.rerun()
