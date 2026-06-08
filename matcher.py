"""
matcher.py  –  Scan body text and insert inline citation markers.

Detection logic (author + year, author-only fallback):
  1. Surname et al. (year)  /  Surname et al., year
  2. Surname (year)         /  Surname, year
  3. Two authors: Surname1 and/& Surname2 [(year)]
  4. Loose: just Surname appearing in text (when no year in text matches)
"""

import re
from typing import List, Tuple, Dict
from reference_parser import Reference
from citation_styles import inline_citation


def _extract_surname(author: str) -> str:
    author = author.strip().rstrip('.,')
    if ',' in author:
        return author.split(',')[0].strip()
    parts = author.split()
    if not parts:
        return author
    # "Smith J" or "Smith JK" format — last token is initials if ≤3 uppercase chars
    if len(parts) >= 2 and re.fullmatch(r'[A-Z]{1,3}', parts[-1]):
        return parts[0]   # "Smith J" → "Smith"
    return parts[-1]      # "John Smith" → "Smith"


def _build_patterns(ref: Reference) -> List[Tuple[re.Pattern, bool]]:
    """
    Returns list of (pattern, is_strict) pairs, best-first.
    Strict = year present in match; loose = surname only.
    """
    patterns = []
    surname = ref.first_author_surname
    if not surname:
        return patterns

    esc = re.escape(surname)
    yr  = re.escape(ref.year) if ref.year else r'(?:19|20)\d{2}'

    # 1. "Smith et al. (2018)" or "Smith et al. 2018" or "Smith et al., 2018"
    patterns.append((re.compile(
        rf'\b{esc}\s+et\s+al\.?\s*[,(]?\s*{yr}[,)]?',
        re.IGNORECASE), True))

    # 2. "Smith (2018)" or "Smith, 2018"
    patterns.append((re.compile(
        rf'\b{esc}\s*[,(]?\s*\(?\s*{yr}\s*\)?',
        re.IGNORECASE), True))

    # 3. Two-author strict: "Smith and Jones (2018)"
    if len(ref.authors) >= 2:
        s2 = re.escape(_extract_surname(ref.authors[1]))
        patterns.append((re.compile(
            rf'\b{esc}\s+(?:and|&)\s+{s2}\s*[,(]?\s*\(?\s*{yr}\s*\)?',
            re.IGNORECASE), True))

    # 4. "Smith et al." without year
    patterns.append((re.compile(
        rf'\b{esc}\s+et\s+al\.?(?!\s*[,(]?\s*(?:19|20)\d{{2}})',
        re.IGNORECASE), False))

    # 5. Two authors without year: "Smith and Jones"
    if len(ref.authors) >= 2:
        s2 = re.escape(_extract_surname(ref.authors[1]))
        patterns.append((re.compile(
            rf'\b{esc}\s+(?:and|&)\s+{s2}(?!\s*[,(]?\s*(?:19|20)\d{{2}})',
            re.IGNORECASE), False))

    # 6. Loose: bare surname (lowest priority)
    patterns.append((re.compile(
        rf'(?<!\w){esc}(?!\w)(?!\s+(?:University|Institute|College|Lab|Center|Hospital|School))',
        re.IGNORECASE), False))

    return patterns


def find_citation_positions(body: str, refs: List[Reference]) \
        -> List[Tuple[int, int, str, int]]:
    """
    Find all positions in body where a citation should be inserted.
    Returns list of (start, end, placeholder, ref_index) sorted by position desc.
    """
    hits: List[Tuple[int, int, str, int]] = []
    claimed: List[Tuple[int, int]] = []

    def overlaps(s, e):
        return any(not (e <= cs or s >= ce) for cs, ce in claimed)

    for ref in refs:
        patterns = _build_patterns(ref)
        found_strict = False

        for pat, is_strict in patterns:
            # If we already have a strict match, skip loose patterns
            if found_strict and not is_strict:
                continue

            for m in pat.finditer(body):
                s, e = m.start(), m.end()
                if overlaps(s, e):
                    continue
                # Skip if already inside a citation bracket [n] or (Author, year)
                before = body[max(0, s-3):s]
                after  = body[e:e+3]
                if re.search(r'\[|\(', before[-1:]) and re.search(r'\]|\)', after[:1]):
                    continue
                hits.append((s, e, f'__CITE_{ref.index}__', ref.index))
                claimed.append((s, e))
                if is_strict:
                    found_strict = True

    hits.sort(key=lambda x: x[0], reverse=True)
    return hits


def insert_citations(body: str, refs: List[Reference], style: str) -> str:
    """Insert formatted inline citations into body text."""
    ref_map: Dict[int, Reference] = {r.index: r for r in refs}
    hits = find_citation_positions(body, refs)

    cited_refs_used = set()
    result = body
    for start, end, placeholder, ref_idx in hits:
        ref = ref_map[ref_idx]
        cite = inline_citation(ref, style)
        # Don't append if cite already present nearby
        after = result[end:end+40]
        if cite in after:
            continue
        # For APA: if the matched text already ends with (year), it IS the citation
        # just reformat it rather than appending a duplicate
        matched = result[start:end]
        import re as _re
        year_already = ref.year and _re.search(r'\(' + _re.escape(ref.year) + r'\)', matched)
        if year_already and style == 'apa':
            # Replace the "Surname (year)" span with "Surname (Cite)"
            new_text = _re.sub(
                r'\s*\(\s*' + _re.escape(ref.year) + r'\s*\)',
                ' ' + cite, matched)
            result = result[:start] + new_text + result[end:]
        else:
            result = result[:end] + ' ' + cite + result[end:]
        cited_refs_used.add(ref_idx)

    return result


def get_cited_ref_indices(body: str, refs: List[Reference]) -> set:
    """Return set of ref indices that were matched in the body."""
    hits = find_citation_positions(body, refs)
    return {ref_idx for _, _, _, ref_idx in hits}
