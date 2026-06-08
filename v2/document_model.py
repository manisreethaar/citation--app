"""
document_model.py
==================
Core model 1: A document is not a flat string.
It is a structured set of sections, each containing sentences,
each sentence having a role (claim / author-observation / transition / method / background).

This is the foundation that makes citation intent detectable.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


# ─── Enums ────────────────────────────────────────────────────────────────────

class SectionType(Enum):
    ABSTRACT     = "abstract"
    INTRODUCTION = "introduction"
    METHODS      = "methods"
    RESULTS      = "results"
    DISCUSSION   = "discussion"
    CONCLUSION   = "conclusion"
    REFERENCES   = "references"
    UNKNOWN      = "unknown"


class SentenceRole(Enum):
    """
    What function does this sentence serve?
    - CLAIM          : asserts something from prior literature → NEEDS citation
    - AUTHOR_OWN     : author's own observation/finding → does NOT need citation
    - BACKGROUND     : general fact, well-known truth → may or may not need citation
    - METHOD         : describes a technique/tool → may need citation
    - TRANSITION     : structural connector → does NOT need citation
    """
    CLAIM        = "claim"
    AUTHOR_OWN   = "author_own"
    BACKGROUND   = "background"
    METHOD       = "method"
    TRANSITION   = "transition"


# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class Sentence:
    text: str
    char_start: int                     # position in original document text
    char_end: int
    section_type: SectionType
    role: SentenceRole
    index: int                          # global sentence index in document

    def __repr__(self):
        return f"[{self.role.value}|{self.section_type.value}] {self.text[:60]}..."


@dataclass
class Section:
    name: str                           # raw heading text
    section_type: SectionType
    char_start: int
    char_end: int
    sentences: List[Sentence] = field(default_factory=list)


@dataclass
class Document:
    raw_text: str
    sections: List[Section] = field(default_factory=list)

    @property
    def all_sentences(self) -> List[Sentence]:
        return [s for sec in self.sections for s in sec.sentences]

    @property
    def body_sentences(self) -> List[Sentence]:
        """All sentences excluding the References section."""
        return [s for sec in self.sections
                if sec.section_type != SectionType.REFERENCES
                for s in sec.sentences]


# ─── Section header patterns ──────────────────────────────────────────────────

_SECTION_PATTERNS = [
    (SectionType.ABSTRACT,     re.compile(r'^\s*abstract\s*$', re.I)),
    (SectionType.INTRODUCTION, re.compile(r'^\s*(?:\d[\.\s]*)?\s*introduction\s*$', re.I)),
    (SectionType.METHODS,      re.compile(r'^\s*(?:\d[\.\s]*)?\s*(?:materials?\s+and\s+)?methods?\s*$', re.I)),
    (SectionType.RESULTS,      re.compile(r'^\s*(?:\d[\.\s]*)?\s*results?\s*$', re.I)),
    (SectionType.DISCUSSION,   re.compile(r'^\s*(?:\d[\.\s]*)?\s*discussion\s*$', re.I)),
    (SectionType.CONCLUSION,   re.compile(r'^\s*(?:\d[\.\s]*)?\s*conclusions?\s*$', re.I)),
    (SectionType.REFERENCES,   re.compile(
        r'^\s*(?:references?|bibliography|works\s+cited|literature\s+cited)\s*$', re.I)),
]


def _detect_section_type(heading: str) -> SectionType:
    for stype, pat in _SECTION_PATTERNS:
        if pat.match(heading):
            return stype
    return SectionType.UNKNOWN


# ─── Sentence role classifiers ────────────────────────────────────────────────

# Phrases that signal the author is reporting their OWN work
_AUTHOR_OWN_SIGNALS = re.compile(
    r'\b(we\s+(found|show|demonstrate|observe|report|propose|present|develop|introduce|conduct|perform|use|apply|evaluate|compare|analyze|test|train|achieve)|'
    r'our\s+(study|work|results?|findings?|model|method|approach|analysis|experiments?|data)|'
    r'in\s+this\s+(study|work|paper|article)|'
    r'this\s+(study|work|paper)\s+(presents?|proposes?|describes?|introduces?)|'
    r'here\s+we|'
    r'the\s+(present|current)\s+study)\b',
    re.I
)

# Phrases that signal a claim from prior literature
_CLAIM_SIGNALS = re.compile(
    r'\b(showed?|demonstrated?|reported?|found|established|proposed?|described?|'
    r'suggested?|indicated?|revealed?|confirmed?|proved?|showed?|'
    r'has\s+been\s+(shown|demonstrated|reported|found|established|proposed|described|suggested)|'
    r'it\s+(is|has\s+been)\s+(well\s+)?(known|established|shown|demonstrated|reported)|'
    r'studies\s+(have\s+)?(shown|demonstrated|reported|found)|'
    r'evidence\s+(suggests?|indicates?|shows?)|'
    r'previously\s+(reported?|described?|demonstrated?|shown)|'
    r'according\s+to)\b',
    re.I
)

# Phrases that signal a method reference
_METHOD_SIGNALS = re.compile(
    r'\b(method|technique|algorithm|protocol|procedure|approach|framework|tool|software|'
    r'package|library|pipeline|workflow|model|architecture|network|classifier|detector|'
    r'using|used|employ|implement|apply|following\s+the\s+(?:method|approach|protocol))\b',
    re.I
)

# Transition words that start structural sentences
_TRANSITION_SIGNALS = re.compile(
    r'^(however|therefore|thus|hence|furthermore|moreover|in\s+(addition|contrast|summary|conclusion)|'
    r'on\s+the\s+other\s+hand|despite|although|nevertheless|consequently|as\s+(a\s+result|mentioned)|'
    r'first|second|third|finally|additionally|similarly|in\s+particular)\b',
    re.I
)


def _classify_sentence_role(text: str, section_type: SectionType) -> SentenceRole:
    """Classify a sentence's role based on its content and section context."""
    stripped = text.strip()

    # Author's own work signals are strongest — check first
    if _AUTHOR_OWN_SIGNALS.search(stripped):
        return SentenceRole.AUTHOR_OWN

    # Transition connectors
    if _TRANSITION_SIGNALS.match(stripped):
        return SentenceRole.TRANSITION

    # In methods section: most sentences are method references or author procedure
    if section_type == SectionType.METHODS:
        if _METHOD_SIGNALS.search(stripped):
            return SentenceRole.METHOD
        return SentenceRole.AUTHOR_OWN  # methods steps are usually author's own

    # Claims from literature
    if _CLAIM_SIGNALS.search(stripped):
        return SentenceRole.CLAIM

    # In introduction/discussion: uncategorized sentences are usually background
    if section_type in (SectionType.INTRODUCTION, SectionType.DISCUSSION):
        return SentenceRole.BACKGROUND

    return SentenceRole.BACKGROUND


# ─── Sentence tokenizer ───────────────────────────────────────────────────────

# Common abbreviations that contain periods but are NOT sentence ends
_ABBREVS = re.compile(
    r'\b(et\s+al|vs|e\.g|i\.e|fig|eq|approx|dept|prof|dr|mr|ms|mrs|'
    r'jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec|'
    r'vol|no|pp|ed|eds|rev|suppl|approx|incl|excl|ref|refs)\.',
    re.I
)

def _tokenize_sentences(text: str, char_offset: int) -> List[tuple]:
    """
    Split text into sentences. Returns list of (sentence_text, char_start, char_end).
    Handles abbreviations, decimal numbers, initials.
    """
    sentences = []
    start = 0
    n = len(text)

    def is_decimal_dot(i: int) -> bool:
        return (
            text[i] == '.'
            and i > 0 and i + 1 < n
            and text[i - 1].isdigit()
            and text[i + 1].isdigit()
        )

    def is_initial_dot(i: int) -> bool:
        return (
            text[i] == '.'
            and i > 0
            and text[i - 1].isupper()
            and (i == 1 or not text[i - 2].isalpha())
        )

    def is_abbrev_dot(i: int) -> bool:
        window_start = max(0, i - 24)
        before = text[window_start:i + 1]
        return bool(_ABBREVS.search(before))

    i = 0
    while i < n:
        ch = text[i]
        if ch not in '.!?':
            i += 1
            continue

        if ch == '.' and (is_decimal_dot(i) or is_initial_dot(i) or is_abbrev_dot(i)):
            i += 1
            continue

        j = i + 1
        while j < n and text[j].isspace():
            j += 1

        is_boundary = j >= n or text[j].isupper() or text[j] in '[('
        if is_boundary:
            raw = text[start:i + 1]
            stripped = raw.strip()
            if stripped:
                leading_ws = len(raw) - len(raw.lstrip())
                sent_start = char_offset + start + leading_ws
                sent_end = char_offset + i + 1
                sentences.append((stripped, sent_start, sent_end))
            start = j
            i = j
        else:
            i += 1

    tail = text[start:]
    stripped = tail.strip()
    if stripped:
        leading_ws = len(tail) - len(tail.lstrip())
        sent_start = char_offset + start + leading_ws
        sent_end = char_offset + n - (len(tail) - len(tail.rstrip()))
        sentences.append((stripped, sent_start, sent_end))

    return sentences


# ─── Main parser ──────────────────────────────────────────────────────────────

def parse_document(text: str) -> Document:
    """
    Parse a full document text into a structured Document object.
    Detects sections, tokenizes sentences, classifies sentence roles.
    """
    lines = text.splitlines(keepends=True)
    doc = Document(raw_text=text)

    # ── Find section boundaries ───────────────────────────────────────────────
    section_breaks = []  # (line_index, section_type, heading_text)
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped:
            stype = _detect_section_type(stripped)
            if stype != SectionType.UNKNOWN:
                section_breaks.append((i, stype, stripped))

    # If no sections detected, treat whole document as one UNKNOWN section
    if not section_breaks:
        section_breaks = [(0, SectionType.UNKNOWN, '')]

    # ── Build sections ────────────────────────────────────────────────────────
    sentence_counter = 0
    for idx, (line_i, stype, heading) in enumerate(section_breaks):
        # Text for this section = from this heading to next heading
        start_line = line_i + 1
        end_line = section_breaks[idx + 1][0] if idx + 1 < len(section_breaks) else len(lines)

        section_text = ''.join(lines[start_line:end_line])
        char_start = sum(len(l) for l in lines[:start_line])
        char_end = char_start + len(section_text)

        section = Section(
            name=heading,
            section_type=stype,
            char_start=char_start,
            char_end=char_end,
        )

        # Skip tokenizing the References section (handled by reference_model.py)
        if stype == SectionType.REFERENCES:
            doc.sections.append(section)
            continue

        # Tokenize and classify sentences
        raw_sentences = _tokenize_sentences(section_text, char_start)
        for sent_text, s_start, s_end in raw_sentences:
            if len(sent_text.strip()) < 10:
                continue
            role = _classify_sentence_role(sent_text, stype)
            sentence = Sentence(
                text=sent_text,
                char_start=s_start,
                char_end=s_end,
                section_type=stype,
                role=role,
                index=sentence_counter,
            )
            section.sentences.append(sentence)
            sentence_counter += 1

        doc.sections.append(section)

    return doc
