"""
reference_model.py
==================
Core model 2: A reference is not a bag of strings.
It is a semantic unit with domain, key concepts, and claim type.

This rich representation is what allows meaningful matching
beyond simple surname + year pattern matching.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Set


# ─── Enums ────────────────────────────────────────────────────────────────────

class ClaimType(Enum):
    """What kind of claim does this reference typically support?"""
    FINDING     = "finding"       # reports a discovery or result
    METHOD      = "method"        # describes a technique, tool, algorithm
    BACKGROUND  = "background"    # provides context or established fact
    DATASET     = "dataset"       # introduces or describes a dataset
    REVIEW      = "review"        # a review or meta-analysis
    UNKNOWN     = "unknown"


class Domain(Enum):
    MEDICINE       = "medicine"
    BIOLOGY        = "biology"
    COMPUTER_SCI   = "computer_science"
    CHEMISTRY      = "chemistry"
    PHYSICS        = "physics"
    STATISTICS     = "statistics"
    ENGINEERING    = "engineering"
    SOCIAL_SCI     = "social_science"
    GENERAL        = "general"


# ─── Domain and claim type classifiers ───────────────────────────────────────

_DOMAIN_KEYWORDS = {
    Domain.MEDICINE: [
        'patient', 'clinical', 'disease', 'therapy', 'treatment', 'diagnosis',
        'hospital', 'trial', 'cancer', 'drug', 'medical', 'surgery', 'symptom',
        'imaging', 'radiology', 'pathology', 'epidemiology', 'cohort', 'placebo'
    ],
    Domain.BIOLOGY: [
        'gene', 'protein', 'cell', 'molecular', 'neural', 'neuron', 'brain',
        'genome', 'dna', 'rna', 'mutation', 'organism', 'species', 'evolution',
        'metabolic', 'enzyme', 'receptor', 'membrane', 'tissue', 'biological'
    ],
    Domain.COMPUTER_SCI: [
        'algorithm', 'neural network', 'deep learning', 'machine learning',
        'classification', 'detection', 'recognition', 'optimization', 'dataset',
        'benchmark', 'model', 'architecture', 'training', 'accuracy', 'convolutional',
        'transformer', 'attention', 'embedding', 'inference', 'latency', 'gpu'
    ],
    Domain.STATISTICS: [
        'regression', 'bayesian', 'probabilistic', 'statistical', 'variance',
        'distribution', 'inference', 'hypothesis', 'significance', 'correlation',
        'sampling', 'estimation', 'bootstrap', 'confidence interval', 'p-value'
    ],
    Domain.CHEMISTRY: [
        'compound', 'synthesis', 'reaction', 'molecule', 'catalyst', 'polymer',
        'solvent', 'oxidation', 'spectroscopy', 'chromatography', 'titration'
    ],
    Domain.ENGINEERING: [
        'system', 'design', 'sensor', 'signal', 'control', 'hardware', 'circuit',
        'voltage', 'frequency', 'wireless', 'network', 'protocol', 'embedded'
    ],
    Domain.SOCIAL_SCI: [
        'survey', 'questionnaire', 'population', 'demographic', 'behavior',
        'psychology', 'cognitive', 'social', 'attitude', 'intervention', 'education'
    ],
}

_CLAIM_TYPE_KEYWORDS = {
    ClaimType.METHOD: [
        'method', 'technique', 'algorithm', 'approach', 'framework', 'tool',
        'pipeline', 'protocol', 'procedure', 'system for', 'using', 'via',
        'network', 'architecture', 'model for', 'based on'
    ],
    ClaimType.REVIEW: [
        'review', 'meta-analysis', 'systematic', 'survey', 'overview',
        'summary', 'meta analysis'
    ],
    ClaimType.DATASET: [
        'dataset', 'database', 'corpus', 'benchmark', 'collection',
        'data for', 'annotated', 'labeled'
    ],
    ClaimType.FINDING: [
        'association', 'effect', 'outcome', 'result', 'finding', 'evidence',
        'demonstrates', 'shows', 'reveals', 'identifies', 'predicts'
    ],
}


def _classify_domain(text: str) -> Domain:
    text_lower = text.lower()
    scores = {}
    for domain, keywords in _DOMAIN_KEYWORDS.items():
        scores[domain] = sum(1 for kw in keywords if kw in text_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else Domain.GENERAL


def _classify_claim_type(title: str) -> ClaimType:
    title_lower = title.lower()
    for ctype, keywords in _CLAIM_TYPE_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return ctype
    return ClaimType.FINDING  # default


# ─── Stopwords (no external library needed) ───────────────────────────────────

_STOPWORDS = {
    'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'shall', 'should', 'may', 'might', 'must', 'can', 'could', 'not', 'no',
    'nor', 'so', 'yet', 'both', 'either', 'neither', 'than', 'as', 'if',
    'its', 'it', 'this', 'that', 'these', 'those', 'which', 'who', 'whom',
    'what', 'when', 'where', 'why', 'how', 'all', 'each', 'every', 'both',
    'few', 'more', 'most', 'other', 'some', 'such', 'into', 'through',
    'during', 'before', 'after', 'above', 'below', 'between', 'out', 'use',
    'using', 'used', 'new', 'based', 'via', 'also', 'their', 'our', 'we',
}


def _extract_noun_phrases(title: str) -> Set[str]:
    """
    Extract meaningful 1-, 2-, and 3-word phrases from a reference title.
    Filters out stopwords and very short tokens.
    Returns lowercase phrases.
    """
    # Tokenize on non-alpha-hyphen
    tokens = re.findall(r"[a-zA-Z][a-zA-Z\-']*", title.lower())
    # Filter stopwords and short tokens
    content_tokens = [t for t in tokens if t not in _STOPWORDS and len(t) > 2]

    phrases: Set[str] = set()
    # Unigrams
    phrases.update(content_tokens)
    # Bigrams
    for i in range(len(content_tokens) - 1):
        phrases.add(f"{content_tokens[i]} {content_tokens[i+1]}")
    # Trigrams
    for i in range(len(content_tokens) - 2):
        phrases.add(f"{content_tokens[i]} {content_tokens[i+1]} {content_tokens[i+2]}")

    return phrases


# ─── Author parsing ───────────────────────────────────────────────────────────

@dataclass
class Author:
    raw: str
    surname: str
    initials: str = ''

    def __str__(self):
        return f"{self.surname}, {self.initials}" if self.initials else self.surname


def _parse_single_author(raw: str) -> Author:
    """Parse one author string into Author object."""
    raw = raw.strip().rstrip('.,')
    if not raw:
        return Author(raw='', surname='', initials='')

    # "Smith, John" or "Smith, J."
    if ',' in raw:
        parts = raw.split(',', 1)
        surname = parts[0].strip()
        rest = parts[1].strip()
        initials = ' '.join(
            p[0].upper() + '.' for p in rest.split() if p and not p.endswith('.')
        ) or rest
        return Author(raw=raw, surname=surname, initials=initials)

    tokens = raw.split()
    if not tokens:
        return Author(raw=raw, surname=raw, initials='')

    # "Smith JK" or "Smith J" — last token is initials (all uppercase, ≤3 chars)
    if len(tokens) >= 2 and re.fullmatch(r'[A-Z]{1,3}\.?', tokens[-1]):
        surname = tokens[0]
        initials = ' '.join(t[0].upper() + '.' for t in tokens[1:])
        return Author(raw=raw, surname=surname, initials=initials)

    # "John Smith" — first tokens are given name, last is surname
    surname = tokens[-1]
    initials = ' '.join(t[0].upper() + '.' for t in tokens[:-1]) if len(tokens) > 1 else ''
    return Author(raw=raw, surname=surname, initials=initials)


def _split_author_string(author_str: str) -> List[Author]:
    """Split multi-author string into list of Author objects."""
    # Normalise "et al."
    author_str = re.sub(r'\bet\s+al\.?', '', author_str, flags=re.I).strip()

    apa_authors = re.findall(
        r'([A-Z][A-Za-z\-]+),\s*((?:[A-Z]\.?\s*){1,4})',
        author_str
    )
    if apa_authors:
        return [
            Author(
                raw=f"{surname}, {initials.strip()}",
                surname=surname.strip(),
                initials=' '.join(
                    f"{c.upper()}." for c in re.findall(r'[A-Z]', initials)
                ),
            )
            for surname, initials in apa_authors
        ]

    # Split on:  ";"  |  ", and "  |  " and "  |  "," before uppercase
    parts = re.split(
        r';\s*|,\s*and\s+(?=[A-Z])|(?<!\w)\band\b(?=\s+[A-Z])|,\s*(?=[A-Z])',
        author_str
    )
    authors = []
    for p in parts:
        p = p.strip().strip('.,')
        if p and len(p) > 1:
            authors.append(_parse_single_author(p))
    return authors


# ─── Reference dataclass ──────────────────────────────────────────────────────

@dataclass
class Reference:
    raw: str
    index: int
    authors: List[Author] = field(default_factory=list)
    year: Optional[str] = None
    title: Optional[str] = None
    journal: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    doi: Optional[str] = None

    # Rich semantic fields
    noun_phrases: Set[str] = field(default_factory=set)
    domain: Domain = Domain.GENERAL
    claim_type: ClaimType = ClaimType.UNKNOWN

    def __post_init__(self):
        if self.title:
            self.noun_phrases = _extract_noun_phrases(self.title)
            self.domain = _classify_domain(
                (self.title or '') + ' ' + (self.journal or '')
            )
            self.claim_type = _classify_claim_type(self.title)

    @property
    def first_author(self) -> Optional[Author]:
        return self.authors[0] if self.authors else None

    @property
    def first_surname(self) -> Optional[str]:
        return self.authors[0].surname if self.authors else None

    @property
    def display_label(self) -> str:
        if not self.authors:
            return f"Ref {self.index}"
        a = self.first_author
        if len(self.authors) == 1:
            label = a.surname
        elif len(self.authors) == 2:
            label = f"{a.surname} & {self.authors[1].surname}"
        else:
            label = f"{a.surname} et al."
        return f"{label} ({self.year or 'n.d.'})"


# ─── Reference list parser ────────────────────────────────────────────────────

_NUMBERED_PREFIX = re.compile(r'^\s*[\[\(]?\d+[\]\).]?\s*')

_PATTERNS = [
    # APA / Vancouver: Authors. (Year). Title...  or  Authors. Year. Title...
    re.compile(
        r'^(?P<authors>[A-Z][^.]+?)[\.,]\s*\(?(?P<year>(?:19|20)\d{2}[a-z]?)\)?[\.,]?\s+(?P<rest>.*)',
        re.DOTALL
    ),
    # Inline year: Authors (Year) Title...
    re.compile(
        r'^(?P<authors>[A-Z][^(]+?)\s*\((?P<year>(?:19|20)\d{2}[a-z]?)\)\s*(?P<rest>.*)',
        re.DOTALL
    ),
]


def _parse_one_entry(raw: str, idx: int) -> Reference:
    ref = Reference(raw=raw, index=idx)

    # Strip leading number
    text = _NUMBERED_PREFIX.sub('', raw).strip()

    # Extract DOI
    doi_m = re.search(r'https?://doi\.org/\S+|doi:\s*\S+', text, re.I)
    if doi_m:
        ref.doi = doi_m.group().strip()

    # Try structured patterns
    for pat in _PATTERNS:
        m = pat.match(text)
        if m:
            ref.authors = _split_author_string(m.group('authors'))
            ref.year = m.group('year')
            _fill_title_journal(ref, m.group('rest'))
            ref.__post_init__()
            return ref

    # Fallback: extract any 4-digit year
    yr = re.search(r'\b((?:19|20)\d{2})\b', text)
    if yr:
        ref.year = yr.group(1)
        before = text[:yr.start()].strip().strip('().,')
        ref.authors = _split_author_string(before) if before else []
        after = text[yr.end():].strip().strip('().,')
        _fill_title_journal(ref, after)

    ref.__post_init__()
    return ref


def _fill_title_journal(ref: Reference, rest: str) -> None:
    """Heuristically extract title + journal + volume/pages from remaining text."""
    # Remove DOI
    rest = re.sub(r'https?://doi\.org/\S+|doi:\s*\S+', '', rest, re.I).strip()

    # Pages at end: 123-456 or pp. 123-456
    pages_m = re.search(r'(?:pp?\.\s*)?([\d]+)[-–]([\d]+)\s*$', rest)
    if pages_m:
        ref.pages = pages_m.group(0).strip()
        rest = rest[:pages_m.start()].strip().strip(',;')

    # Volume/issue: 12(3) or vol. 12
    vol_m = re.search(
        r'(?:vol(?:ume)?\.?\s*)?(\d+)\s*(?:\((\d+)\))?\s*[:;,]?\s*$', rest, re.I
    )
    if vol_m and vol_m.group(1):
        ref.volume = vol_m.group(1)
        ref.issue = vol_m.group(2)
        rest = rest[:vol_m.start()].strip().strip(',;')

    # First sentence = title, second = journal
    sentences = re.split(r'\.\s+', rest, maxsplit=2)
    if sentences:
        ref.title = sentences[0].strip().strip('"\'')
    if len(sentences) > 1:
        ref.journal = sentences[1].strip().strip('.,')


def _merge_wrapped_lines(text: str) -> List[str]:
    """Join soft-wrapped reference lines into single entries."""
    entries, current = [], ''
    for line in text.splitlines():
        line = line.rstrip()
        if not line.strip():
            if current:
                entries.append(current.strip())
                current = ''
            continue
        if _NUMBERED_PREFIX.match(line):
            if current:
                entries.append(current.strip())
            current = line
        elif line and line[0].isupper() and len(current.split('.')) > 3:
            entries.append(current.strip())
            current = line
        else:
            current += ' ' + line if current else line
    if current:
        entries.append(current.strip())
    return [e for e in entries if len(e) > 15]


def parse_reference_section(ref_text: str) -> List[Reference]:
    """Parse the reference section text into a list of Reference objects."""
    entries = _merge_wrapped_lines(ref_text)
    return [_parse_one_entry(e, i + 1) for i, e in enumerate(entries)]


def split_body_and_references(text: str):
    """
    Split document into (body_text, ref_section_text).
    Returns (full_text, '') if no reference section found.
    """
    _REF_HEADER = re.compile(
        r'^\s*(?:references?|bibliography|works\s+cited|literature\s+cited)\s*$',
        re.I | re.M
    )
    m = _REF_HEADER.search(text)
    if m:
        return text[:m.start()], text[m.end():].lstrip('\r\n')

    # Fallback: numbered block near end
    lines = text.splitlines()
    _NUM = re.compile(r'^\s*[\[\(]?\d+[\]\).]?\s+')
    for i in range(len(lines) - 1, max(len(lines) - 150, 0), -1):
        if _NUM.match(lines[i]):
            body = '\n'.join(lines[:i])
            refs = '\n'.join(lines[i:])
            return body, refs

    return text, ''
