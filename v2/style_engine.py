"""
style_engine.py
================
Format inline citation markers and bibliography entries for all supported styles.
Completely independent of how citations were detected — just takes a Reference
and returns properly formatted strings.

Supported: apa | vancouver | ieee | nature
"""

import re
from typing import List
from reference_model import Reference, Author


SUPPORTED_STYLES = ['apa', 'vancouver', 'ieee', 'nature']

_SUPERSCRIPT = str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹')


# ─── Inline markers ───────────────────────────────────────────────────────────

def inline_marker(ref: Reference, style: str) -> str:
    """Return the in-text citation string for a reference."""
    style = style.lower()
    if style == 'apa':
        return _apa_inline(ref)
    elif style in ('vancouver', 'ieee'):
        return f'[{ref.index}]'
    elif style == 'nature':
        return str(ref.index).translate(_SUPERSCRIPT)
    raise ValueError(f"Unsupported style: {style}. Choose from: {SUPPORTED_STYLES}")


def _apa_inline(ref: Reference) -> str:
    year = ref.year or 'n.d.'
    authors = ref.authors
    if not authors:
        label = ref.journal or ref.title or 'Anon'
    elif len(authors) == 1:
        label = authors[0].surname
    elif len(authors) == 2:
        label = f"{authors[0].surname} & {authors[1].surname}"
    else:
        label = f"{authors[0].surname} et al."
    return f'({label}, {year})'


# ─── Bibliography formatters ──────────────────────────────────────────────────

def format_bibliography(refs: List[Reference], style: str) -> str:
    """Format a complete bibliography section."""
    style = style.lower()
    header = 'References\n' + '─' * 60
    entries = [header] + [format_entry(r, style) for r in refs]
    return '\n\n'.join(entries)


def format_entry(ref: Reference, style: str) -> str:
    style = style.lower()
    if style == 'apa':       return _apa_entry(ref)
    if style == 'vancouver': return _vancouver_entry(ref)
    if style == 'ieee':      return _ieee_entry(ref)
    if style == 'nature':    return _nature_entry(ref)
    return f'{ref.index}. {ref.raw}'


# ── APA 7th edition ───────────────────────────────────────────────────────────

def _apa_entry(ref: Reference) -> str:
    parts = []

    if ref.authors:
        parts.append(_apa_author_list(ref.authors))

    parts.append(f'({ref.year or "n.d."}).')

    if ref.title:
        parts.append(f'{ref.title}.')

    journal_str = _journal_block_apa(ref)
    if journal_str:
        parts.append(journal_str)

    if ref.doi:
        doi = ref.doi if ref.doi.startswith('http') else f'https://doi.org/{ref.doi}'
        parts.append(doi)

    result = ' '.join(parts)
    return re.sub(r'\.{2,}', '.', result)


def _apa_author_list(authors: List[Author]) -> str:
    fmt = [_apa_format_author(a) for a in authors]
    if len(fmt) > 20:
        return ', '.join(fmt[:19]) + ', ... ' + fmt[-1] + '.'
    if len(fmt) == 1:
        s = fmt[0]
        return s if s.endswith('.') else s + '.'
    last = fmt[-1]
    suffix = '' if last.endswith('.') else '.'
    return ', '.join(fmt[:-1]) + ', & ' + last + suffix


def _apa_format_author(author: Author) -> str:
    if not author.initials:
        return author.surname
    # Ensure initials are dotted: "J K" → "J. K."
    inits = re.sub(r'([A-Z])(?!\.)', r'\1.', author.initials.replace(' ', '. '))
    inits = re.sub(r'\.{2,}', '.', inits)
    return f'{author.surname}, {inits}'


def _journal_block_apa(ref: Reference) -> str:
    parts = []
    if ref.journal:
        parts.append(ref.journal)
    if ref.volume:
        v = ref.volume
        if ref.issue:
            v += f'({ref.issue})'
        parts.append(v)
    if ref.pages:
        parts.append(ref.pages)
    return ', '.join(parts) + '.' if parts else ''


# ── Vancouver (ICMJE) ─────────────────────────────────────────────────────────

def _vancouver_entry(ref: Reference) -> str:
    parts = [f'{ref.index}.']

    if ref.authors:
        parts.append(_vancouver_author_list(ref.authors))

    if ref.title:
        parts.append(f'{ref.title}.')

    jpart = _journal_block_vancouver(ref)
    if jpart:
        parts.append(jpart)

    if ref.doi:
        doi_str = ref.doi.strip()
        if not doi_str.lower().startswith('doi'):
            doi_str = 'doi: ' + doi_str
        parts.append(doi_str)

    return ' '.join(parts)


def _vancouver_author_list(authors: List[Author]) -> str:
    fmt = []
    for a in authors[:6]:
        inits = a.initials.replace('.', '').replace(' ', '')
        fmt.append(f'{a.surname} {inits}' if inits else a.surname)
    result = ', '.join(fmt)
    if len(authors) > 6:
        result += ', et al.'
    return result + '.'


def _journal_block_vancouver(ref: Reference) -> str:
    parts = []
    if ref.journal:
        parts.append(ref.journal)
    if ref.year:
        parts.append(ref.year)
    if ref.volume:
        v = ref.volume
        if ref.issue:
            v += f'({ref.issue})'
        parts.append(v)
    if ref.pages:
        parts.append(ref.pages)
    return ';'.join(parts[:2]) + ';' + parts[2] + ':' + parts[3] + '.' \
        if len(parts) == 4 else (', '.join(parts) + '.' if parts else '')


# ── IEEE ──────────────────────────────────────────────────────────────────────

def _ieee_entry(ref: Reference) -> str:
    parts = [f'[{ref.index}]']

    if ref.authors:
        parts.append(_ieee_author_list(ref.authors))

    if ref.title:
        parts.append(f'"{ref.title},"')

    if ref.journal:
        parts.append(f'{ref.journal},')

    vol_str = ''
    if ref.volume:
        vol_str = f'vol. {ref.volume}'
        if ref.issue:
            vol_str += f', no. {ref.issue}'
        vol_str += ','
    if vol_str:
        parts.append(vol_str)

    if ref.pages:
        parts.append(f'pp. {ref.pages},')

    if ref.year:
        parts.append(f'{ref.year}.')

    if ref.doi:
        doi_str = ref.doi.strip()
        if not doi_str.lower().startswith('doi'):
            doi_str = 'doi: ' + doi_str
        parts.append(doi_str + '.')

    return ' '.join(parts)


def _ieee_author_list(authors: List[Author]) -> str:
    fmt = []
    for a in authors:
        if a.initials:
            inits = '. '.join(
                c for c in a.initials.replace(' ', '').replace('.', '')
            ) + '.'
            fmt.append(f'{inits} {a.surname}')
        else:
            fmt.append(a.surname)
    if len(fmt) == 1:
        return fmt[0] + ','
    return ', '.join(fmt[:-1]) + ' and ' + fmt[-1] + ','


# ── Nature ────────────────────────────────────────────────────────────────────

def _nature_entry(ref: Reference) -> str:
    parts = [f'{ref.index}.']

    if ref.authors:
        parts.append(_nature_author_list(ref.authors))

    if ref.title:
        parts.append(f'{ref.title}.')

    if ref.journal:
        parts.append(ref.journal)

    vp = []
    if ref.volume:
        vp.append(ref.volume)
    if ref.pages:
        vp.append(ref.pages)
    if ref.year:
        vp.append(f'({ref.year})')
    if vp:
        parts.append(', '.join(vp) + '.')

    if ref.doi:
        doi_str = ref.doi.strip()
        if not doi_str.startswith('http'):
            doi_str = 'https://doi.org/' + doi_str
        parts.append(doi_str)

    return ' '.join(parts)


def _nature_author_list(authors: List[Author]) -> str:
    fmt = []
    for a in authors[:10]:
        if a.initials:
            inits = '.'.join(
                c for c in a.initials.replace(' ', '').replace('.', '')
            ) + '.'
            fmt.append(f'{a.surname}, {inits}')
        else:
            fmt.append(a.surname)
    result = ', '.join(fmt)
    if len(authors) > 10:
        result += ' et al.'
    return result
