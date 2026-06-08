"""
citation_inventory.py
======================
Pre-pass: scan the document for existing citation markers BEFORE doing
anything else. Resolve each marker to a reference, record where it was,
then strip all markers cleanly from the text.

This correctly solves style conversion: we know what [1] meant before
we removed it, so we can reinsert it in any target style accurately.

Existing marker formats detected:
  [1]          [1,2,3]       [1-3]
  (Smith, 2020)              (Smith et al., 2020)
  ¹ ² ³        ¹·²           superscript Unicode
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from reference_model import Reference


# ─── Detected citation dataclass ──────────────────────────────────────────────

@dataclass
class DetectedCitation:
    raw_text: str               # e.g. "[1]" or "(Smith, 2020)"
    char_start: int
    char_end: int
    ref_indices: List[int]      # resolved reference index/indices
    style_detected: str         # "numbered", "author_year", "superscript"


# ─── Regex patterns for existing citation formats ─────────────────────────────

# Numbered: [1], [1,2], [1-3], [1, 2, 3]
_NUMBERED_CITE = re.compile(r'\[(\d+(?:[,\-]\s*\d+)*)\]')

# Author-year: (Smith, 2020) or (Smith et al., 2020) or (Smith & Jones, 2020)
_AUTHOR_YEAR_CITE = re.compile(
    r'\(([A-Z][a-z]+(?:\s+et\s+al\.?|\s*&\s*[A-Z][a-z]+)?),?\s*((?:19|20)\d{2}[a-z]?)\)'
)

# Superscript Unicode: ¹²³⁴⁵⁶⁷⁸⁹⁰ or combinations like ¹·²·³
_SUPERSCRIPT_MAP = {'⁰':'0','¹':'1','²':'2','³':'3','⁴':'4',
                    '⁵':'5','⁶':'6','⁷':'7','⁸':'8','⁹':'9'}
_SUPERSCRIPT_CITE = re.compile(r'[⁰¹²³⁴⁵⁶⁷⁸⁹]+(?:[·,][⁰¹²³⁴⁵⁶⁷⁸⁹]+)*')


def _super_to_int(s: str) -> Optional[int]:
    try:
        return int(''.join(_SUPERSCRIPT_MAP.get(c, '') for c in s if c in _SUPERSCRIPT_MAP))
    except ValueError:
        return None


def _resolve_numbered(ref_indices_str: str) -> List[int]:
    """Turn "1,2-4" into [1, 2, 3, 4]."""
    indices = []
    for part in re.split(r',\s*', ref_indices_str):
        part = part.strip()
        if '-' in part:
            lo, hi = part.split('-', 1)
            try:
                indices.extend(range(int(lo), int(hi) + 1))
            except ValueError:
                pass
        else:
            try:
                indices.append(int(part))
            except ValueError:
                pass
    return indices


def _resolve_author_year(surname: str, year: str,
                          refs: List[Reference]) -> List[int]:
    """Find reference index by matching author surname + year."""
    surname = surname.strip().lower()
    year = year.strip()
    matches = []
    for ref in refs:
        if ref.first_surname and ref.first_surname.lower() == surname:
            if ref.year == year:
                matches.append(ref.index)
    return matches


# ─── Main inventory builder ───────────────────────────────────────────────────

def build_citation_inventory(text: str,
                              refs: List[Reference]) -> List[DetectedCitation]:
    """
    Scan text for all existing citation markers.
    Returns list of DetectedCitation objects sorted by position.
    """
    found: List[DetectedCitation] = []

    # ── Numbered citations ────────────────────────────────────────────────────
    for m in _NUMBERED_CITE.finditer(text):
        indices = _resolve_numbered(m.group(1))
        if any(1 <= i <= len(refs) for i in indices):
            found.append(DetectedCitation(
                raw_text=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
                ref_indices=[i for i in indices if 1 <= i <= len(refs)],
                style_detected='numbered',
            ))

    # ── Author-year citations ─────────────────────────────────────────────────
    for m in _AUTHOR_YEAR_CITE.finditer(text):
        surname_part = m.group(1)
        # Extract just the first surname (before "et al" or "&")
        surname = re.split(r'\s+et\s+al|&', surname_part, flags=re.I)[0].strip()
        year = m.group(2)
        indices = _resolve_author_year(surname, year, refs)
        if indices:
            found.append(DetectedCitation(
                raw_text=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
                ref_indices=indices,
                style_detected='author_year',
            ))

    # ── Superscript citations ─────────────────────────────────────────────────
    for m in _SUPERSCRIPT_CITE.finditer(text):
        parts = re.split(r'[·,]', m.group(0))
        indices = []
        for p in parts:
            n = _super_to_int(p)
            if n is not None and 1 <= n <= len(refs):
                indices.append(n)
        if indices:
            found.append(DetectedCitation(
                raw_text=m.group(0),
                char_start=m.start(),
                char_end=m.end(),
                ref_indices=indices,
                style_detected='superscript',
            ))

    # Sort by position, deduplicate overlapping
    found.sort(key=lambda x: x.char_start)
    deduped = []
    last_end = -1
    for dc in found:
        if dc.char_start >= last_end:
            deduped.append(dc)
            last_end = dc.char_end

    return deduped


def strip_existing_citations(text: str,
                              inventory: List[DetectedCitation]) -> str:
    """
    Remove all detected citation markers from text.
    Works right-to-left to preserve character positions.
    """
    result = text
    for dc in sorted(inventory, key=lambda x: x.char_start, reverse=True):
        # Remove the marker and any surrounding whitespace (but keep one space)
        start = dc.char_start
        end = dc.char_end
        # Trim a leading space if the marker was space-prefixed
        if start > 0 and result[start - 1] == ' ':
            start -= 1
        result = result[:start] + result[end:]
    return result


def build_sentence_inventory(inventory: List[DetectedCitation],
                              sentences) -> Dict[int, List[int]]:
    """
    Map sentence index → list of reference indices that were already cited
    at/near that sentence (from the pre-pass inventory).
    Used by the scoring engine as Signal F.
    """
    mapping: Dict[int, List[int]] = {}
    for dc in inventory:
        for sent in sentences:
            # Citation marker falls within or immediately after this sentence
            if sent.char_start <= dc.char_start <= sent.char_end + 5:
                mapping.setdefault(sent.index, []).extend(dc.ref_indices)
    return mapping
