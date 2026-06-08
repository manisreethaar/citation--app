"""
citation_detector.py  –  Detect what citation mode a document body already uses.

Returns one of four modes:
  'numbered'    – body already has [1], [2] or (1), (2) markers  → Vancouver/IEEE/Nature
  'superscript' – body already has ¹²³ unicode superscripts       → Nature/AMA
  'author_year' – body already has (Smith, 2020) style markers    → APA/Harvard/Chicago
  'author_only' – body has bare surname mentions but no year      → partial / MLA-ish
  'none'        – no detectable existing citation markers

Usage:
    from citation_detector import detect_citation_mode
    info = detect_citation_mode(body_text)
    # info = {
    #   'mode': 'numbered',
    #   'count': 42,
    #   'examples': ['[1]', '[2]', '[3]'],
    #   'style_guess': 'vancouver',
    #   'markers': [(start, end, number), ...],
    # }
"""

import re
from typing import List, Tuple, Dict, Any

# ── Patterns ───────────────────────────────────────────────────────────────────

# [1] [2] [1,2] [1-3] [1,2,3]  (square bracket, mandatory number)
_BRACKET_NUM_RE = re.compile(
    r'\[(\d+(?:[,\-–]\s*\d+)*)\]'
)

# (1) (2) (1,2)  (round bracket number — common in some Vancouver variants)
_PAREN_NUM_RE = re.compile(
    r'(?<!\()(\((\d{1,3}(?:[,\-]\s*\d{1,3})*)\))(?!\s*(?:19|20)\d{2})'
)

# Unicode superscripts: ¹²³ etc.
_SUPERSCRIPT_RE = re.compile(
    r'[⁰¹²³⁴⁵⁶⁷⁸⁹]+'
)

# (Author, 2020) / (Author et al., 2020) / (Author & Jones, 2020)
_AUTHOR_YEAR_RE = re.compile(
    r'\([A-Z][a-zA-Zéàü\-]+'         # first author surname
    r'(?:\s+(?:et\s+al\.|and|\&)\s+[A-Z][a-zA-Z\-]+)?'  # optional second
    r',?\s+(?:19|20)\d{2}[a-z]?\)',   # year
    re.IGNORECASE
)

# "Author (2020)" inline — used in some author-year styles
_AUTHOR_PAREN_YEAR_RE = re.compile(
    r'[A-Z][a-zA-Z\-]+\s+\((?:19|20)\d{2}[a-z]?\)'
)


def detect_citation_mode(body: str) -> Dict[str, Any]:
    """
    Analyse body text and return a dict describing existing citation style.
    """
    # --- Numbered [n] ---
    bracket_hits = list(_BRACKET_NUM_RE.finditer(body))
    if len(bracket_hits) >= 2:
        markers = [(m.start(), m.end(), m.group(1)) for m in bracket_hits[:10]]
        return {
            'mode':        'numbered',
            'count':       len(bracket_hits),
            'examples':    [m.group() for m in bracket_hits[:5]],
            'style_guess': 'vancouver',
            'markers':     markers,
            'description': f'Found {len(bracket_hits)} numbered citation markers like [1], [2], [3]',
        }

    # --- Superscript ¹²³ ---
    sup_hits = list(_SUPERSCRIPT_RE.finditer(body))
    if len(sup_hits) >= 2:
        return {
            'mode':        'superscript',
            'count':       len(sup_hits),
            'examples':    [m.group() for m in sup_hits[:5]],
            'style_guess': 'nature',
            'markers':     [(m.start(), m.end(), m.group()) for m in sup_hits[:10]],
            'description': f'Found {len(sup_hits)} superscript citation markers like ¹, ², ³',
        }

    # --- (1) (2) round-bracket numbered ---
    paren_hits = list(_PAREN_NUM_RE.finditer(body))
    if len(paren_hits) >= 3:
        return {
            'mode':        'numbered',
            'count':       len(paren_hits),
            'examples':    [m.group(1) for m in paren_hits[:5]],
            'style_guess': 'vancouver',
            'markers':     [(m.start(), m.end(), m.group(2)) for m in paren_hits[:10]],
            'description': f'Found {len(paren_hits)} numbered citation markers like (1), (2)',
        }

    # --- Author-year ---
    ay_hits  = list(_AUTHOR_YEAR_RE.finditer(body))
    apy_hits = list(_AUTHOR_PAREN_YEAR_RE.finditer(body))
    all_ay   = ay_hits + apy_hits

    if len(all_ay) >= 2:
        return {
            'mode':        'author_year',
            'count':       len(all_ay),
            'examples':    [m.group() for m in all_ay[:5]],
            'style_guess': 'apa',
            'markers':     [(m.start(), m.end(), m.group()) for m in all_ay[:10]],
            'description': f'Found {len(all_ay)} author-date markers like (Smith, 2020)',
        }

    return {
        'mode':        'none',
        'count':       0,
        'examples':    [],
        'style_guess': 'unknown',
        'markers':     [],
        'description': 'No existing citation markers detected — will insert from scratch',
    }


def extract_cited_numbers(body: str) -> List[int]:
    """
    Return sorted list of all unique reference numbers cited in body.
    Handles [1], [1,2], [1-3] etc.
    """
    nums = set()
    for m in _BRACKET_NUM_RE.finditer(body):
        token = m.group(1)
        # Ranges: 1-3 → 1,2,3
        for part in re.split(r',\s*', token):
            part = part.strip()
            rng = re.match(r'(\d+)\s*[-–]\s*(\d+)', part)
            if rng:
                nums.update(range(int(rng.group(1)), int(rng.group(2)) + 1))
            elif part.isdigit():
                nums.add(int(part))
    return sorted(nums)


def cited_number_positions(body: str) -> List[Tuple[int, int, List[int]]]:
    """
    Return list of (start, end, [numbers]) for every citation marker in body.
    E.g. "[1,3]" → (10, 15, [1, 3])
    """
    results = []
    for m in _BRACKET_NUM_RE.finditer(body):
        nums = []
        for part in re.split(r',\s*', m.group(1)):
            part = part.strip()
            rng = re.match(r'(\d+)\s*[-–]\s*(\d+)', part)
            if rng:
                nums.extend(range(int(rng.group(1)), int(rng.group(2)) + 1))
            elif part.isdigit():
                nums.append(int(part))
        if nums:
            results.append((m.start(), m.end(), nums))
    return results
