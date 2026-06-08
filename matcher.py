"""
matcher.py  –  Scan body text and insert / reformat inline citation markers.

Three operating modes (auto-detected):
  'numbered'    – body already has [1],[2] → reformat to chosen style
  'author_year' – body already has (Smith, 2020) → re-tag to chosen style
  'none'        – no existing markers → scan for author+year and insert

Detection logic for author+year matching:
  1. Surname et al. (year)  /  Surname et al., year
  2. Surname (year)         /  Surname, year
  3. Two authors: Surname1 and/& Surname2 [(year)]
  4. "et al." without year (loose)
  5. Two authors without year (loose)
  6. Loose: just Surname appearing in text (lowest priority)
"""

import re
from typing import List, Tuple, Dict, Optional
from reference_parser import Reference
from citation_styles import inline_citation
from citation_detector import detect_citation_mode, cited_number_positions


# ── Author surname extractor ───────────────────────────────────────────────────

def _extract_surname(author: str) -> str:
    author = author.strip().rstrip('.,')
    if ',' in author:
        return author.split(',')[0].strip()
    parts = author.split()
    if not parts:
        return author
    if len(parts) >= 2 and re.fullmatch(r'[A-Z]{1,3}\.?', parts[-1]):
        return parts[0]
    return parts[-1]


# ── Pattern builder for author+year matching ───────────────────────────────────

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
        rf'(?<!\w){esc}(?!\w)(?!\s+(?:University|Institute|College|Lab|Center|Hospital|School|Department))',
        re.IGNORECASE), False))

    return patterns


# ── Mode A: insert by author+year matching ─────────────────────────────────────

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
        patterns     = _build_patterns(ref)
        found_strict = False

        for pat, is_strict in patterns:
            if found_strict and not is_strict:
                continue

            for m in pat.finditer(body):
                s, e = m.start(), m.end()
                if overlaps(s, e):
                    continue
                # Skip if already inside a citation bracket [n] or (Author, year)
                before = body[max(0, s - 3):s]
                after  = body[e:e + 3]
                if re.search(r'[\[{(]', before[-1:]) and re.search(r'[\])}]', after[:1]):
                    continue
                hits.append((s, e, f'__CITE_{ref.index}__', ref.index))
                claimed.append((s, e))
                if is_strict:
                    found_strict = True

    hits.sort(key=lambda x: x[0], reverse=True)
    return hits


def insert_citations(body: str, refs: List[Reference], style: str) -> str:
    """Insert formatted inline citations into body text (author+year mode)."""
    ref_map: Dict[int, Reference] = {r.index: r for r in refs}
    hits = find_citation_positions(body, refs)

    result = body
    for start, end, placeholder, ref_idx in hits:
        ref  = ref_map[ref_idx]
        cite = inline_citation(ref, style)
        after = result[end:end + 40]
        if cite in after:
            continue
        # APA: if matched text already ends with (year), reformat inline
        matched = result[start:end]
        year_already = ref.year and re.search(
            r'\(' + re.escape(ref.year) + r'\)', matched)
        if year_already and style in ('apa', 'harvard'):
            new_text = re.sub(
                r'\s*\(\s*' + re.escape(ref.year) + r'\s*\)',
                ' ' + cite, matched)
            result = result[:start] + new_text + result[end:]
        else:
            result = result[:end] + ' ' + cite + result[end:]

    return result


# ── Mode B: reformat existing [n] numbered citations ──────────────────────────

def reformat_numbered_citations(body: str, refs: List[Reference],
                                target_style: str) -> str:
    """
    Body already has [1], [2], [1,3], [1-3] etc.

    If target_style is numbered (vancouver/ieee/nature/ama):
        Keep [n] markers but normalise formatting.
    If target_style is author-year (apa/harvard/chicago/mla):
        Replace [n] with (Author, Year) style.
    """
    ref_map: Dict[int, Reference] = {r.index: r for r in refs}
    numbered_styles = {'vancouver', 'ieee', 'nature', 'ama'}

    positions = cited_number_positions(body)
    if not positions:
        return body

    # Process in reverse order so offsets stay valid
    result = body
    for start, end, nums in sorted(positions, key=lambda x: x[0], reverse=True):
        if target_style in numbered_styles:
            # Keep as [n] / normalise commas
            new_cite = '[' + ','.join(str(n) for n in sorted(nums)) + ']'
        else:
            # Replace with author-year for each number
            parts = []
            for n in sorted(nums):
                ref = ref_map.get(n)
                if ref:
                    parts.append(inline_citation(ref, target_style))
                else:
                    parts.append(f'[{n}]')
            new_cite = '; '.join(parts)
            if target_style in ('apa', 'harvard', 'chicago'):
                # Wrap multiple in one set of parens if they all have same author year format
                # e.g. (Smith, 2020; Jones, 2021)
                # Strip outer parens from each part then rewrap
                stripped = [p.strip('()') for p in parts]
                new_cite = '(' + '; '.join(stripped) + ')'

        result = result[:start] + new_cite + result[end:]

    return result


# ── Mode C: reformat existing (Author, Year) author-year citations ─────────────

def reformat_author_year_citations(body: str, refs: List[Reference],
                                   target_style: str) -> str:
    """
    Body has (Smith, 2020) style citations.
    Replace with target_style inline markers.

    For numbered target styles → inserts [n] by looking up which ref matches.
    For author-year styles     → reformats the existing markers.
    """
    # Build surname+year → ref_index mapping
    lookup: Dict[Tuple[str, str], int] = {}
    for ref in refs:
        if ref.first_author_surname and ref.year:
            key = (ref.first_author_surname.lower(), ref.year)
            lookup[key] = ref.index

    # Match existing author-year markers
    marker_re = re.compile(
        r'\(([A-Z][a-zA-Z\-]+)(?:\s+et\s+al\.?)?\s*,?\s*((?:19|20)\d{2}[a-z]?)\)',
        re.IGNORECASE
    )

    result   = body
    numbered_styles = {'vancouver', 'ieee', 'nature', 'ama'}
    ref_map  = {r.index: r for r in refs}

    for m in reversed(list(marker_re.finditer(body))):
        surname = m.group(1).strip().lower()
        year    = m.group(2).strip()

        # Find best matching ref
        ref_idx = lookup.get((surname, year))
        if ref_idx is None:
            # Try surname-only match
            for (sn, yr), idx in lookup.items():
                if sn == surname:
                    ref_idx = idx
                    break

        if ref_idx is None:
            continue

        ref = ref_map.get(ref_idx)
        if not ref:
            continue

        new_cite = inline_citation(ref, target_style)
        result   = result[:m.start()] + new_cite + result[m.end():]

    return result


# ── Smart dispatch: choose correct mode ───────────────────────────────────────

def smart_insert_citations(body: str, refs: List[Reference],
                            target_style: str) -> Tuple[str, str]:
    """
    Auto-detect existing citation mode and apply the right transformation.

    Returns:
        (cited_body, mode_description)
    """
    mode_info = detect_citation_mode(body)
    mode      = mode_info['mode']

    if mode == 'numbered':
        cited = reformat_numbered_citations(body, refs, target_style)
        desc  = (f"Detected {mode_info['count']} existing [{'{n}'}] numbered citations. "
                 f"Reformatted to {target_style.upper()} style.")
    elif mode == 'superscript':
        # Treat superscript same as numbered — convert positions
        cited = body  # superscript reformatting is complex; keep as-is for now
        desc  = (f"Detected {mode_info['count']} superscript citations (¹²³). "
                 f"Bibliography reformatted to {target_style.upper()}.")
    elif mode == 'author_year':
        if target_style in ('apa', 'harvard', 'chicago', 'mla'):
            cited = reformat_author_year_citations(body, refs, target_style)
            desc  = (f"Detected {mode_info['count']} existing author-year citations. "
                     f"Reformatted to {target_style.upper()} style.")
        else:
            cited = reformat_author_year_citations(body, refs, target_style)
            desc  = (f"Detected {mode_info['count']} existing author-year citations. "
                     f"Converted to {target_style.upper()} numbered style.")
    else:
        cited = insert_citations(body, refs, target_style)
        desc  = f"No existing citations detected. Inserted {target_style.upper()} citations from author-year matching."

    return cited, desc


# ── Utilities ─────────────────────────────────────────────────────────────────

def get_cited_ref_indices(body: str, refs: List[Reference]) -> set:
    """Return set of ref indices matched in the body (any mode)."""
    mode_info = detect_citation_mode(body)
    if mode_info['mode'] == 'numbered':
        from citation_detector import extract_cited_numbers
        return set(extract_cited_numbers(body))
    hits = find_citation_positions(body, refs)
    return {ref_idx for _, _, _, ref_idx in hits}
