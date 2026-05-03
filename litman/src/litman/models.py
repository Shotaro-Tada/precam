from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Author(BaseModel):
    given: str = ""
    family: str = ""

    def full_name(self) -> str:
        return f"{self.given} {self.family}".strip()


class Paper(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str
    authors: list[Author] = []
    year: Optional[int] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    journal: Optional[str] = None
    journal_abbrev: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    publisher: Optional[str] = None
    abstract: Optional[str] = None
    url: str
    tags: list[str] = []
    notes: str = ""
    added_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(timespec="seconds")
    )
    bibtex_key: Optional[str] = None

    def model_post_init(self, __context) -> None:
        if self.bibtex_key is None:
            self.bibtex_key = self._generate_bibtex_key()

    def _generate_bibtex_key(self) -> str:
        first = self.authors[0].family.lower() if self.authors else "unknown"
        first = "".join(c for c in first if c.isascii() and c.isalpha())
        year = str(self.year) if self.year else "nd"
        stop = {"a", "an", "the", "of", "for", "and", "in", "on", "with", "to", "from"}
        word = ""
        for w in (self.title or "").split():
            candidate = "".join(c for c in w.lower() if c.isalpha())
            if candidate and candidate not in stop:
                word = candidate
                break
        return f"{first}{year}{word}"
