from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import click

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from .bibtex import export_library_bib, generate_bibtex
from .fetchers import fetch_metadata
from .importer import bibtex_to_papers
from .models import Paper
from .zotero_sync import sync_collections
from .search import filter_papers, search_papers
from .store import (
    delete_paper,
    find_duplicate,
    get_library_dir,
    load_all_papers,
    load_paper,
    save_paper,
)


@click.group()
@click.option("--library", "-l", type=click.Path(), default=None, envvar="LITMAN_LIBRARY",
              help="Library directory (default: ./library)")
@click.pass_context
def cli(ctx, library):
    """litman — lightweight literature manager"""
    ctx.ensure_object(dict)
    ctx.obj["library"] = Path(library) if library else None


def _lib(ctx) -> Path | None:
    return ctx.obj.get("library")


@cli.command()
@click.argument("url")
@click.option("--tags", "-t", multiple=True, help="Tags to apply")
@click.pass_context
def add(ctx, url, tags):
    """Add a paper by URL."""
    lib = _lib(ctx)

    click.echo(f"Fetching metadata from {url} ...")
    try:
        paper = fetch_metadata(url)
    except Exception as e:
        click.echo(f"Error fetching metadata: {e}", err=True)
        raise SystemExit(1)

    dup = find_duplicate(paper.doi, url, lib)

    if tags:
        paper.tags = list(tags)

    path = save_paper(paper, lib)
    click.echo(f"Added: [{paper.id}] {paper.title}")
    if dup:
        click.echo(f"  Note: duplicate of [{dup.id}] {dup.title[:60]}")
    click.echo(f"  Authors: {', '.join(a.full_name() for a in paper.authors)}")
    click.echo(f"  Year: {paper.year}  DOI: {paper.doi or 'N/A'}")
    click.echo(f"  Saved to: {path}")


@cli.command("list")
@click.option("--tag", "-t", multiple=True, help="Filter by tag")
@click.option("--year", "-y", type=int, help="Filter by year")
@click.option("--journal", "-j", help="Filter by journal (substring)")
@click.pass_context
def list_papers(ctx, tag, year, journal):
    """List all papers in the library."""
    papers = load_all_papers(_lib(ctx))
    if tag:
        papers = filter_papers(papers, tags=list(tag))
    if year:
        papers = filter_papers(papers, year_from=year, year_to=year)
    if journal:
        papers = filter_papers(papers, journal=journal)

    if not papers:
        click.echo("No papers found.")
        return

    papers.sort(key=lambda p: (p.year or 0, p.title), reverse=True)
    for p in papers:
        authors = ", ".join(a.full_name() for a in p.authors[:3])
        if len(p.authors) > 3:
            authors += " et al."
        tags_str = f" [{', '.join(p.tags)}]" if p.tags else ""
        click.echo(f"  {p.id}  {p.year or '----'}  {p.title[:60]}")
        click.echo(f"          {authors}{tags_str}")


@cli.command()
@click.argument("query")
@click.pass_context
def search(ctx, query):
    """Search the library by keyword."""
    papers = load_all_papers(_lib(ctx))
    results = search_papers(papers, query)
    if not results:
        click.echo("No results.")
        return

    click.echo(f"Found {len(results)} paper(s):")
    for p in results:
        click.echo(f"  {p.id}  {p.year or '----'}  {p.title[:70]}")


@cli.command()
@click.argument("paper_id")
@click.pass_context
def show(ctx, paper_id):
    """Show details of a paper."""
    try:
        p = load_paper(paper_id, _lib(ctx))
    except FileNotFoundError:
        click.echo(f"Paper not found: {paper_id}", err=True)
        raise SystemExit(1)

    click.echo(f"Title:     {p.title}")
    click.echo(f"Authors:   {', '.join(a.full_name() for a in p.authors)}")
    click.echo(f"Year:      {p.year or 'N/A'}")
    click.echo(f"Journal:   {p.journal or 'N/A'}")
    click.echo(f"DOI:       {p.doi or 'N/A'}")
    click.echo(f"ArXiv:     {p.arxiv_id or 'N/A'}")
    click.echo(f"URL:       {p.url}")
    click.echo(f"Tags:      {', '.join(p.tags) if p.tags else 'none'}")
    click.echo(f"BibTeX key:{p.bibtex_key}")
    click.echo(f"Added:     {p.added_at}")
    if p.abstract:
        click.echo(f"\nAbstract:\n  {p.abstract[:500]}")
    if p.notes:
        click.echo(f"\nNotes:\n  {p.notes}")


@cli.command()
@click.argument("paper_id")
@click.confirmation_option(prompt="Are you sure you want to delete this paper?")
@click.pass_context
def delete(ctx, paper_id):
    """Remove a paper from the library."""
    try:
        p = load_paper(paper_id, _lib(ctx))
    except FileNotFoundError:
        click.echo(f"Paper not found: {paper_id}", err=True)
        raise SystemExit(1)

    delete_paper(paper_id, _lib(ctx))
    click.echo(f"Deleted: {p.title}")


@cli.command()
@click.argument("paper_id")
@click.option("--add-tag", "-t", multiple=True, help="Add tags")
@click.option("--remove-tag", "-r", multiple=True, help="Remove tags")
@click.option("--notes", "-n", help="Set notes")
@click.pass_context
def edit(ctx, paper_id, add_tag, remove_tag, notes):
    """Edit paper tags or notes."""
    lib = _lib(ctx)
    try:
        paper = load_paper(paper_id, lib)
    except FileNotFoundError:
        click.echo(f"Paper not found: {paper_id}", err=True)
        raise SystemExit(1)

    if add_tag:
        paper.tags = list(set(paper.tags) | set(add_tag))
    if remove_tag:
        paper.tags = [t for t in paper.tags if t not in remove_tag]
    if notes is not None:
        paper.notes = notes

    paper.updated_at = datetime.now().isoformat(timespec="seconds")
    save_paper(paper, lib)
    click.echo(f"Updated: {paper.title}")
    click.echo(f"  Tags: {', '.join(paper.tags) if paper.tags else 'none'}")


@cli.command()
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output .bib file (default: library/library.bib)")
@click.pass_context
def export(ctx, output):
    """Export library to BibTeX."""
    lib = _lib(ctx)
    papers = load_all_papers(lib)
    if not papers:
        click.echo("Library is empty.")
        return

    out = Path(output) if output else get_library_dir(lib) / "library.bib"
    click.echo(f"Exporting {len(papers)} paper(s) to {out} ...")
    export_library_bib(papers, out)
    click.echo("Done.")


@cli.command()
@click.argument("paper_id")
@click.pass_context
def bib(ctx, paper_id):
    """Print BibTeX entry for a single paper."""
    try:
        paper = load_paper(paper_id, _lib(ctx))
    except FileNotFoundError:
        click.echo(f"Paper not found: {paper_id}", err=True)
        raise SystemExit(1)

    click.echo(generate_bibtex(paper))


@cli.command("import")
@click.argument("bib_file", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Show what would be imported without saving")
@click.pass_context
def import_bib(ctx, bib_file, dry_run):
    """Import papers from a BibTeX file (e.g. Zotero export)."""
    lib = _lib(ctx)
    path = Path(bib_file)

    click.echo(f"Parsing {path.name} ...")
    papers = bibtex_to_papers(path)
    click.echo(f"Found {len(papers)} entries.")

    added = 0
    skipped = 0
    for paper in papers:
        dup = find_duplicate(paper.doi, paper.url, lib)
        if dup:
            skipped += 1
            continue
        if dry_run:
            click.echo(f"  [dry-run] {paper.bibtex_key}: {paper.title[:70]}")
        else:
            save_paper(paper, lib)
        added += 1

    if dry_run:
        click.echo(f"\nDry run: {added} would be added, {skipped} duplicates skipped.")
    else:
        click.echo(f"\nImported {added} papers, skipped {skipped} duplicates.")


@cli.command("zotero-sync")
@click.argument("zotero_db", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Show what would change without saving")
@click.pass_context
def zotero_sync(ctx, zotero_db, dry_run):
    """Sync Zotero collection (folder) structure as tags."""
    lib = _lib(ctx)
    click.echo(f"Reading Zotero database: {zotero_db}")
    updated, unmatched = sync_collections(Path(zotero_db), lib, dry_run=dry_run)
    mode = "Dry run" if dry_run else "Synced"
    click.echo(f"{mode}: {updated} papers updated with folder tags, {unmatched} Zotero items unmatched.")


if __name__ == "__main__":
    cli()
