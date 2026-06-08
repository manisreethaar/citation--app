"""
reference_parser.py
--------------------
Extracts and parses the reference list from the end of a document.

Handles ALL major reference formats:
  • Vancouver / IEEE:  1. Smith J, Jones A. Title. J Abbrev. 2020;10(2):1-5.
  • APA 7th:           Smith, J., & Jones, A. (2020). Title. Journal, 10(2), 1-5.
  • Harvard:           Smith, J. and Jones, A. (2020) 'Title', Journal, 10(2), 1-5.
  • MLA 9th:           Smith, John, and Alice Jones. "Title." Journal 10.2 (2020): 1-5.
  • Chicago 17th:      Smith, John, and Alice Jones. "Title." Journal 10, no. 2 (2020): 1-5.
  • Nature/Cell:       Smith, J. & Jones, A. Title. Journal 10, 1-5 (2020).
  • IEEE bracket:      [1] J. Smith and A. Jones, "Title," Journal, vol. 10, no. 2, pp. 1-5, 2020.
  • AMA:               1. Smith JK, Jones AL. Title. Journal. 2020;10(2):1-5.
  • DOI-only:          https://doi.org/10.xxxx/yyyy
  • URL references:    https://www.example.com/article (accessed 2020)
  • Book references:   Author. Title. Publisher; Year.
  • Preprints:         Author. Title. bioRxiv/arXiv. Year. doi:xxx
"""

import re
from dataclasses import dataclass, field
from typing import Optional, List, Tuple


# ── Reference dataclass ────────────────────────────────────────────────────────

@dataclass
class Reference:
    """Represents a single parsed reference."""
    raw:                 str
    index:               int
    authors:             List[str]          = field(default_factory=list)
    year:                Optional[str]      = None
    title:               Optional[str]      = None
    journal:             Optional[str]      = None
    volume:              Optional[str]      = None
    issue:               Optional[str]      = None
    pages:               Optional[str]      = None
    doi:                 Optional[str]      = None
    url:                 Optional[str]      = None
    publisher:           Optional[str]      = None
    ref_type:            str                = 'article'   # article|book|web|preprint
    first_author_surname:Optional[str]      = None

    def __post_init__(self):
        if self.authors:
            self.first_author_surname = _extract_surname(self.authors[0])

    @property
    def display_author(self) -> str:
        if not self.authors:
            return 'Unknown'
        if len(self.authors) == 1:
            return self.first_author_surname or self.authors[0]
        if len(self.authors) == 2:
            return f"{self.first_author_surname} & {_extract_surname(self.authors[1])}"
        return f"{self.first_author_surname} et al."


def _extract_surname(author: str) -> str:
    author = author.strip().rstrip('.,')
    if ',' in author:
        return author.split(',')[0].strip()
    parts = author.split()
    if not parts:
        return author
    # "Smith J" or "Smith JK" → surname is first token
    if len(parts) >= 2 and re.fullmatch(r'[A-Z]{1,3}\.?', parts[-1]):
        return parts[0]
    # "John Smith" → last word is surname
    return parts[-1]


# ── Reference section detection ────────────────────────────────────────────────

_REF_SECTION_HEADINGS = re.compile(
    r'^\s*(?:'
    r'references?'
    r'|bibliography'
    r'|works?\s+cited'
    r'|literature\s+cited'
    r'|citations?'
    r'|sources?'
    r'|reference\s+list'
    r'|further\s+reading'
    r'|endnotes?'
    r')\s*$',
    re.IGNORECASE
)

# Numbered entry starters: "1.", "[1]", "(1)", "1 "
_NUMBERED_START_RE = re.compile(r'^\s*(?:\[(\d+)\]|\((\d+)\)|(\d+)\.)\s+')

# Author-year entry starters: "Smith, J. (2020)" or "Smith J (2020)"
_AUTHOR_YEAR_START_RE = re.compile(
    r'^[A-Z][a-zA-Zéàü\-\']+,?\s+[A-Z]?\.?\s*(?:&|and)?\s*.*?\(?(?:19|20)\d{2}\)?'
)


def split_references_from_body(text: str) -> Tuple[str, str]:
    """
    Split document text into (body, references_section).

    Strategies (in order):
    1. Match a known heading line exactly
    2. Match all-caps "REFERENCES" heading
    3. Numbered block starting near the end (fallback)
    """
    lines = text.splitlines()
    n = len(lines)

    # Strategy 1: exact heading match
    for i, line in enumerate(lines):
        stripped = line.strip()
        if _REF_SECTION_HEADINGS.match(stripped):
            body = '\n'.join(lines[:i])
            refs = '\n'.join(lines[i + 1:])
            return body, refs

    # Strategy 2: ALL-CAPS heading e.g. "REFERENCES" "BIBLIOGRAPHY"
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped in ('REFERENCES', 'BIBLIOGRAPHY', 'WORKS CITED',
                        'LITERATURE CITED', 'REFERENCE LIST', 'CITATIONS'):
            body = '\n'.join(lines[:i])
            refs = '\n'.join(lines[i + 1:])
            return body, refs

    # Strategy 3: find first numbered entry in the last 40% of document
    start_search = max(0, int(n * 0.6))
    for i in range(start_search, n):
        if _NUMBERED_START_RE.match(lines[i]):
            # Confirm at least 2 more numbered entries follow
            subsequent = sum(
                1 for j in range(i + 1, min(i + 20, n))
                if _NUMBERED_START_RE.match(lines[j])
            )
            if subsequent >= 2:
                body = '\n'.join(lines[:i])
                refs = '\n'.join(lines[i:])
                return body, refs

    # Strategy 4: author-year block near end
    for i in range(start_search, n):
        if _AUTHOR_YEAR_START_RE.match(lines[i]):
            subsequent = sum(
                1 for j in range(i + 1, min(i + 10, n))
                if _AUTHOR_YEAR_START_RE.match(lines[j])
            )
            if subsequent >= 2:
                body = '\n'.join(lines[:i])
                refs = '\n'.join(lines[i:])
                return body, refs

    return text, ''


# ── Entry joiner ───────────────────────────────────────────────────────────────

def _join_wrapped_lines(text: str) -> List[str]:
    """
    Merge wrapped reference lines into single entries.
    Handles both numbered and author-year styles.
    """
    raw_lines = [l.rstrip() for l in text.splitlines()]
    entries   = []
    current   = ''

    def is_new_entry(line: str) -> bool:
        return bool(_NUMBERED_START_RE.match(line)
                    or _AUTHOR_YEAR_START_RE.match(line))

    for line in raw_lines:
        if not line.strip():
            if current:
                entries.append(current.strip())
                current = ''
            continue

        if is_new_entry(line):
            if current:
                entries.append(current.strip())
            current = line
        elif current:
            # Continuation line — append with space
            current += ' ' + line.strip()
        else:
            current = line

    if current:
        entries.append(current.strip())

    return [e for e in entries if len(e.strip()) > 10]


# ── Author string parser ────────────────────────────────────────────────────────

def parse_authors(author_str: str) -> List[str]:
    """
    Split a raw author string into individual author names.
    Handles:
      "Smith J, Jones A, Brown B"          (Vancouver/AMA)
      "Smith, John and Jones, Alice"        (APA/Harvard)
      "Smith, J., & Jones, A."             (APA)
      "J. Smith and A. Jones"              (IEEE)
      "Smith, John, Alice Jones and Brown" (MLA)
    """
    if not author_str:
        return []

    s = author_str.strip()

    # Normalise "et al." → keep as single token
    s = re.sub(r'\bet\s+al\.?', '\x00ET_AL\x00', s, flags=re.IGNORECASE)

    # Split on semicolons first (most unambiguous)
    if ';' in s:
        parts = re.split(r';\s*', s)
    # Split on " and " / " & " when NOT followed by initials that suggest
    # it's part of a compound surname
    elif re.search(r'\s+(?:and|&)\s+', s, re.IGNORECASE):
        parts = re.split(r'\s+(?:and|&)\s+', s, flags=re.IGNORECASE)
    # Split on commas that precede capital letters (surname, GivenInitial pattern)
    # but NOT "Smith, J., Jones" — so we look for ", [Capital]" where Capital
    # is followed by more than just "." (i.e. a new surname)
    elif re.search(r',\s+[A-Z][a-z]', s):
        parts = _split_apa_authors(s)
    # Simple comma split for "Smith J, Jones A"
    elif re.search(r',\s*[A-Z]{1,2}\.?\s*(?:,|$)', s):
        parts = re.split(r',\s*(?=[A-Z][a-z])', s)
    else:
        parts = re.split(r',\s*', s)

    cleaned = []
    for p in parts:
        p = p.replace('\x00ET_AL\x00', 'et al.')
        p = p.strip().strip('.,')
        if p and len(p) > 1 and p.lower() not in ('and', '&', 'et al.', 'et al'):
            cleaned.append(p)

    return cleaned[:20]  # cap at 20 authors


def _split_apa_authors(s: str) -> List[str]:
    """
    Handle APA-style author strings: "Smith, J., Jones, A., & Brown, B."
    """
    # Temporarily protect "Surname, Initial." pattern
    # Replace "Smith, J." with "Smith|J." to avoid splitting there
    protected = re.sub(r'([A-Z][a-z]+),\s*([A-Z]\.)', r'\1|\2', s)
    # Now split on ", " that precede a capital
    parts = re.split(r',\s*(?=[A-Z])', protected)
    # Restore
    return [p.replace('|', ', ') for p in parts]


# ── Format-specific parsers ────────────────────────────────────────────────────

def _parse_doi(text: str) -> Optional[str]:
    m = re.search(
        r'(?:https?://doi\.org/|doi:\s*)(\S+)',
        text, re.IGNORECASE
    )
    if m:
        doi = m.group(0).strip().rstrip('.,)')
        return doi if doi.startswith('http') else 'https://doi.org/' + m.group(1).rstrip('.,)')
    return None


def _parse_url(text: str) -> Optional[str]:
    m = re.search(r'https?://(?!doi\.org)\S+', text)
    if m:
        return m.group().rstrip('.,)')
    return None


def _parse_year(text: str) -> Optional[str]:
    m = re.search(r'\b((?:19|20)\d{2})\b', text)
    return m.group(1) if m else None


def _parse_pages(text: str) -> Optional[str]:
    m = re.search(r'(?:pp?\.?\s*)?(\d+)\s*[-–]\s*(\d+)', text)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.search(r'(?:pp?\.?\s*)(\d+)$', text.rstrip('.,;'))
    if m:
        return m.group(1)
    return None


def _parse_vol_issue(text: str) -> Tuple[Optional[str], Optional[str]]:
    # "10(2)" or "vol. 10, no. 2" or "10:xxx" (Vancouver)
    m = re.search(r'(?:vol\.?\s*)?(\d+)\s*[(\[]\s*(\d+)\s*[)\]]', text, re.IGNORECASE)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r'(?:vol\.?\s*)(\d+)\s*(?:,\s*no\.?\s*(\d+))?', text, re.IGNORECASE)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r'\b(\d{1,3})\s*\((\d{1,3})\)', text)
    if m:
        return m.group(1), m.group(2)
    return None, None


def _parse_vancouver_entry(text: str) -> dict:
    """
    Parse Vancouver/AMA entry:
    Smith J, Jones A, Brown B. Title of article. J Abbreviation. 2020;10(2):1-5.
    """
    result = {}

    # Year: "2020;10(2):1-5" or "2020;10:1-5" or just "2020."
    vm = re.search(r'\b((?:19|20)\d{2})\s*;?\s*(\d+)?\s*(?:\((\d+)\))?\s*:?\s*([\d-–]+)?', text)
    if vm:
        result['year']  = vm.group(1)
        result['volume']= vm.group(2)
        result['issue'] = vm.group(3)
        result['pages'] = vm.group(4).replace('–', '-') if vm.group(4) else None
        text_before = text[:vm.start()]
    else:
        result['year'] = _parse_year(text)
        text_before = text

    # Split into author + title + journal by "." separators
    sentences = [s.strip() for s in re.split(r'\.\s+', text_before) if s.strip()]
    if sentences:
        result['authors'] = parse_authors(sentences[0])
    if len(sentences) > 1:
        result['title']   = sentences[1].strip('"\'')
    if len(sentences) > 2:
        result['journal'] = sentences[2].strip('.,')

    return result


def _parse_ieee_entry(text: str) -> dict:
    """
    Parse IEEE entry:
    [1] J. Smith and A. Jones, "Title of article," Journal Name, vol. 10, no. 2, pp. 1-5, 2020.
    """
    result = {}
    result['year']   = _parse_year(text)
    result['pages']  = _parse_pages(text)
    vol, issue       = _parse_vol_issue(text)
    result['volume'] = vol
    result['issue']  = issue

    # Title in quotes
    tm = re.search(r'["""](.*?)["""]', text)
    if tm:
        result['title'] = tm.group(1).strip()
        # Authors before title
        before = text[:tm.start()].strip().strip(',')
        result['authors'] = parse_authors(before)
        # Journal after title
        after = text[tm.end():]
        jm = re.match(r',?\s*([^,]+)', after)
        if jm:
            result['journal'] = jm.group(1).strip().strip(',.')
    else:
        # No quoted title — best-effort
        result['authors'] = []
        result['title']   = None
        result['journal'] = None

    return result


def _parse_apa_entry(text: str) -> dict:
    """
    Parse APA entry:
    Smith, J., & Jones, A. (2020). Title of article. Journal Name, 10(2), 1-5.
    """
    result = {}

    # Year in parentheses
    ym = re.search(r'\(((?:19|20)\d{2}[a-z]?)\)', text)
    if ym:
        result['year']  = ym.group(1)
        before = text[:ym.start()].strip().rstrip('.,')
        after  = text[ym.end():].strip().lstrip('.,').strip()
    else:
        result['year']  = _parse_year(text)
        before = ''
        after  = text

    result['authors'] = parse_authors(before) if before else []
    result['pages']   = _parse_pages(after)
    vol, issue        = _parse_vol_issue(after)
    result['volume']  = vol
    result['issue']   = issue

    # Remove vol/issue/pages from after to get title + journal
    clean = re.sub(r'\d+\s*\(\d+\)\s*,?\s*[\d–-]+\.?', '', after).strip()
    clean = re.sub(r'\bvol\.?\s*\d+.*', '', clean, flags=re.IGNORECASE).strip()
    parts = re.split(r'\.\s+', clean, maxsplit=2)
    if parts:
        result['title']   = parts[0].strip().strip('"\'')
    if len(parts) > 1:
        result['journal'] = parts[1].strip().strip('.,')

    return result


def _parse_nature_entry(text: str) -> dict:
    """
    Parse Nature/Cell entry:
    Smith, J. & Jones, A. Title of article. Nature 10, 1-5 (2020).
    """
    result = {}

    # Year at end in parentheses
    ym = re.search(r'\(((?:19|20)\d{2})\)\s*\.?\s*$', text)
    if ym:
        result['year'] = ym.group(1)
        text_core = text[:ym.start()].strip().rstrip('.')
    else:
        result['year']  = _parse_year(text)
        text_core = text

    result['pages']  = _parse_pages(text_core)
    vol, issue       = _parse_vol_issue(text_core)
    result['volume'] = vol
    result['issue']  = issue

    # Remove vol/pages from end
    core = re.sub(r'\d+[,\s]+[\d–-]+\s*$', '', text_core).strip()
    parts = re.split(r'\.\s+', core, maxsplit=2)
    if parts:
        result['authors'] = parse_authors(parts[0])
    if len(parts) > 1:
        result['title']   = parts[1].strip()
    if len(parts) > 2:
        result['journal'] = parts[2].strip('.,')
    elif result.get('title'):
        # Nature format: "Title. Journal vol,"
        jm = re.search(r'\.\s+([A-Z][^\d]+?)\s+\d', text_core)
        if jm:
            result['journal'] = jm.group(1).strip()

    return result


def _parse_mla_entry(text: str) -> dict:
    """
    Parse MLA entry:
    Smith, John, and Alice Jones. "Title of Article." Journal Name, vol. 10, no. 2, 2020, pp. 1-5.
    """
    result = {}
    result['year']   = _parse_year(text)
    result['pages']  = _parse_pages(text)
    vol, issue       = _parse_vol_issue(text)
    result['volume'] = vol
    result['issue']  = issue

    tm = re.search(r'["""](.*?)["""]', text)
    if tm:
        result['title']   = tm.group(1).strip()
        result['authors'] = parse_authors(text[:tm.start()])
        after = text[tm.end():].strip().strip('.,')
        jm = re.match(r'([A-Za-z][^,]+)', after)
        if jm:
            result['journal'] = jm.group(1).strip('.,')
    else:
        parts = re.split(r'\.\s+', text, maxsplit=3)
        result['authors'] = parse_authors(parts[0]) if parts else []
        result['title']   = parts[1].strip('"\'') if len(parts) > 1 else None
        result['journal'] = parts[2].strip('.,')  if len(parts) > 2 else None

    return result


def _detect_ref_format(text: str) -> str:
    """
    Guess what format a single reference entry is in.
    Returns: 'vancouver' | 'ieee' | 'apa' | 'nature' | 'mla' | 'generic'
    """
    # IEEE: has quoted title and vol./no./pp.
    if re.search(r'["""].*?["""]', text) and re.search(r'vol\.?\s*\d+', text, re.I):
        return 'ieee'
    # Vancouver/AMA: year in "2020;vol(issue):pages" pattern
    if re.search(r'\b(19|20)\d{2}\s*;\s*\d+', text):
        return 'vancouver'
    # APA: year in parentheses near start
    if re.search(r'\((19|20)\d{2}[a-z]?\)\.', text):
        return 'apa'
    # Nature: year in parentheses at END
    if re.search(r'\((19|20)\d{2}\)\s*\.?\s*$', text):
        return 'nature'
    # MLA: quoted title present
    if re.search(r'["""].*?["""]', text):
        return 'mla'
    return 'generic'


# ── Master entry parser ────────────────────────────────────────────────────────

def _parse_entry(raw: str, idx: int) -> Reference:
    """Parse a single reference entry string into a Reference object."""
    ref = Reference(raw=raw, index=idx)

    # Strip leading number/bracket
    text = _NUMBERED_START_RE.sub('', raw).strip()

    # Extract DOI/URL first
    ref.doi = _parse_doi(text)
    ref.url = _parse_url(text) if not ref.doi else None

    # DOI-only reference
    if ref.doi and len(text.replace(ref.doi, '').strip()) < 5:
        ref.ref_type = 'article'
        return ref

    # Web/URL reference
    if ref.url:
        ref.ref_type = 'web'
        # Try to get title from text around URL
        title_part = text.replace(ref.url, '').strip().strip('.,')
        if title_part:
            parts = re.split(r'\.\s+', title_part, maxsplit=2)
            ref.authors = parse_authors(parts[0]) if parts else []
            ref.title   = parts[1].strip() if len(parts) > 1 else title_part
        ref.year = _parse_year(text)
        if ref.authors:
            ref.first_author_surname = _extract_surname(ref.authors[0])
        return ref

    # Detect format and delegate
    fmt = _detect_ref_format(text)

    if fmt == 'ieee':
        d = _parse_ieee_entry(text)
    elif fmt == 'vancouver':
        d = _parse_vancouver_entry(text)
    elif fmt == 'apa':
        d = _parse_apa_entry(text)
    elif fmt == 'nature':
        d = _parse_nature_entry(text)
    elif fmt == 'mla':
        d = _parse_mla_entry(text)
    else:
        d = _parse_generic_entry(text)

    # Apply parsed fields
    for k, v in d.items():
        if v is not None and hasattr(ref, k):
            setattr(ref, k, v)

    if ref.authors:
        ref.first_author_surname = _extract_surname(ref.authors[0])
    return ref


def _parse_generic_entry(text: str) -> dict:
    """
    Fallback parser: handle anything not matched above.
    Tries year-based splitting, then period-based splitting.
    """
    result = {}
    result['year']  = _parse_year(text)
    result['pages'] = _parse_pages(text)
    vol, issue      = _parse_vol_issue(text)
    result['volume']= vol
    result['issue'] = issue
    result['doi']   = _parse_doi(text)

    ym = re.search(r'\b((?:19|20)\d{2})\b', text)
    if ym:
        before = text[:ym.start()].strip().rstrip('().,')
        after  = text[ym.end():].strip().lstrip('().,').strip()
        result['authors'] = parse_authors(before) if before else []
        parts = re.split(r'\.\s+', after, maxsplit=2)
        result['title']   = parts[0].strip().strip('"\'') if parts else None
        result['journal'] = parts[1].strip('.,') if len(parts) > 1 else None
    else:
        parts = re.split(r'\.\s+', text, maxsplit=3)
        result['authors'] = parse_authors(parts[0]) if parts else []
        result['title']   = parts[1].strip('"\'') if len(parts) > 1 else None
        result['journal'] = parts[2].strip('.,')  if len(parts) > 2 else None

    return result


# ── Public API ─────────────────────────────────────────────────────────────────

def parse_references(ref_section_text: str) -> List[Reference]:
    """Parse a block of reference text into a list of Reference objects."""
    entries = _join_wrapped_lines(ref_section_text)
    refs = []
    for i, entry in enumerate(entries, start=1):
        if entry.strip():
            refs.append(_parse_entry(entry, i))
    return refs


def parse_references_from_full_text(full_text: str):
    """Convenience: split body + refs section, then parse."""
    body, ref_section = split_references_from_body(full_text)
    if not ref_section.strip():
        return body, []
    return body, parse_references(ref_section)
