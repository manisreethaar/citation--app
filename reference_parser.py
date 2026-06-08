"""
reference_parser.py
--------------------
Extracts and parses the reference list from the end of a document.
Supports common reference formats found in academic journals.
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List, Tuple


@dataclass
class Reference:
    """Represents a single parsed reference."""
    raw: str
    index: int
    authors: List[str] = field(default_factory=list)
    year: Optional[str] = None
    title: Optional[str] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    doi: Optional[str] = None
    first_author_surname: Optional[str] = None

    def __post_init__(self):
        if self.authors:
            self.first_author_surname = _extract_surname(self.authors[0])


def _extract_surname(author: str) -> str:
    import re as _re
    author = author.strip().rstrip('.,')
    if ',' in author:
        return author.split(',')[0].strip()
    parts = author.split()
    if not parts:
        return author
    # "Smith J" or "Smith JK" → surname is first token, last is initials
    if len(parts) >= 2 and _re.fullmatch(r'[A-Z]{1,3}\.?', parts[-1]):
        return parts[0]
    return parts[-1]


_REF_SECTION_RE = re.compile(
    r'^\s*(?:references?|bibliography|works\s+cited|literature\s+cited'
    r'|citations?|sources?)\s*$',
    re.IGNORECASE
)

_NUMBERED_RE = re.compile(r'^\s*[\[\(]?\d+[\]\).]?\s+')

_AUTHOR_YEAR_BLOCK_RE = re.compile(
    r'^([A-Z][^.]+?)\.?\s*\(?((?:19|20)\d{2}[a-z]?)\)?\.?\s+(.*)',
    re.DOTALL
)

_INLINE_YEAR_RE = re.compile(
    r'^([A-Z][^(]+?)\s*\(((?:19|20)\d{2}[a-z]?)\)\s*(.*)',
    re.DOTALL
)


def split_references_from_body(text: str) -> Tuple[str, str]:
    """Split document text into (body, references_section)."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if _REF_SECTION_RE.match(line):
            body = '\n'.join(lines[:i])
            refs = '\n'.join(lines[i+1:])
            return body, refs
    # Fallback: numbered block near end
    for i in range(len(lines) - 1, max(len(lines) - 200, 0), -1):
        if _NUMBERED_RE.match(lines[i]):
            body = '\n'.join(lines[:i])
            refs = '\n'.join(lines[i:])
            return body, refs
    return text, ''


def _join_wrapped_lines(text: str) -> List[str]:
    """Merge wrapped reference lines into single entries."""
    raw_lines = [l.rstrip() for l in text.splitlines()]
    entries = []
    current = ''
    for line in raw_lines:
        if not line.strip():
            if current:
                entries.append(current.strip())
                current = ''
            continue
        if _NUMBERED_RE.match(line):
            if current:
                entries.append(current.strip())
            current = line
        elif line and line[0].isupper() and not current:
            current = line
        elif line and line[0].isupper() and current and len(current.split('.')) > 2:
            entries.append(current.strip())
            current = line
        else:
            current += ' ' + line if current else line
    if current:
        entries.append(current.strip())
    return [e for e in entries if len(e) > 15]


def parse_authors(author_str: str) -> List[str]:
    """Split an author string into individual author names."""
    author_str = re.sub(r'\bet\s+al\.?', 'et al', author_str, flags=re.IGNORECASE)
    parts = re.split(r';\s*|,\s*(?:and\s+)?(?=[A-Z])|(?<!\s)(?:\s+and\s+)', author_str)
    cleaned = []
    for p in parts:
        p = p.strip().strip('.,')
        if p and len(p) > 1:
            cleaned.append(p)
    return cleaned


def _parse_entry(raw: str, idx: int) -> Reference:
    ref = Reference(raw=raw, index=idx)
    text = _NUMBERED_RE.sub('', raw).strip()

    doi_m = re.search(r'https?://doi\.org/\S+|doi:\s*\S+', text, re.IGNORECASE)
    if doi_m:
        ref.doi = doi_m.group().strip()

    m = _AUTHOR_YEAR_BLOCK_RE.match(text)
    if m:
        ref.authors = parse_authors(m.group(1))
        ref.year = m.group(2)
        _fill_title_journal(ref, m.group(3))
        ref.first_author_surname = _extract_surname(ref.authors[0]) if ref.authors else None
        return ref

    m = _INLINE_YEAR_RE.match(text)
    if m:
        ref.authors = parse_authors(m.group(1))
        ref.year = m.group(2)
        _fill_title_journal(ref, m.group(3))
        ref.first_author_surname = _extract_surname(ref.authors[0]) if ref.authors else None
        return ref

    yr_m = re.search(r'\b((?:19|20)\d{2})\b', text)
    if yr_m:
        ref.year = yr_m.group(1)
        before = text[:yr_m.start()].strip().strip('().,')
        ref.authors = parse_authors(before) if before else []
        after = text[yr_m.end():].strip().strip('().,')
        _fill_title_journal(ref, after)

    if ref.authors:
        ref.first_author_surname = _extract_surname(ref.authors[0])
    return ref


def _fill_title_journal(ref: Reference, rest: str) -> None:
    rest = re.sub(r'https?://doi\.org/\S+|doi:\s*\S+', '', rest, flags=re.IGNORECASE).strip()

    pages_m = re.search(r'(?:pp?\.\s*)?([\d]+)[-–]([\d]+)\s*$', rest)
    if pages_m:
        ref.pages = pages_m.group(0).strip()
        rest = rest[:pages_m.start()].strip().strip(',;')

    vol_m = re.search(r'(?:vol\.?\s*)?(\d+)\s*(?:\((\d+)\))?\s*[:;,]?\s*$', rest, re.IGNORECASE)
    if vol_m and vol_m.group(1):
        ref.volume = vol_m.group(1)
        if vol_m.group(2):
            ref.issue = vol_m.group(2)
        rest = rest[:vol_m.start()].strip().strip(',;')

    sentences = re.split(r'\.\s+', rest, maxsplit=2)
    if sentences:
        ref.title = sentences[0].strip().strip('"\'')
    if len(sentences) > 1:
        ref.journal = sentences[1].strip().strip('.,')


def parse_references(ref_section_text: str) -> List[Reference]:
    """Parse a block of reference text into a list of Reference objects."""
    entries = _join_wrapped_lines(ref_section_text)
    refs = []
    for i, entry in enumerate(entries, start=1):
        refs.append(_parse_entry(entry, i))
    return refs
