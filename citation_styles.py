"""
citation_styles.py  –  Format inline citations and bibliography entries.

Supported styles: apa | vancouver | ieee | nature | mla | chicago | harvard | ama
"""


import re
from typing import List
from reference_parser import Reference


# ─── Inline citation markers ──────────────────────────────────────────────────

def inline_citation(ref: Reference, style: str, superscript: bool = False) -> str:
    """Return the inline citation string for the given reference and style."""
    style = style.lower()
    if style == 'apa':       return _apa_inline(ref)
    elif style in ('vancouver', 'ieee'): return f'[{ref.index}]'
    elif style == 'nature':  return _to_superscript(str(ref.index)) if superscript else f'[{ref.index}]'
    elif style == 'mla':     return _mla_inline(ref)
    elif style == 'chicago': return _chicago_inline(ref)
    elif style == 'harvard': return _harvard_inline(ref)
    elif style == 'ama':     return _to_superscript(str(ref.index))
    raise ValueError(f"Unknown style: {style}")


def _apa_inline(ref: Reference) -> str:
    year = ref.year or 'n.d.'
    if not ref.authors:
        label = ref.journal or ref.title or 'Anon'
    elif len(ref.authors) == 1:
        label = _surname(ref.authors[0])
    elif len(ref.authors) == 2:
        label = f"{_surname(ref.authors[0])} & {_surname(ref.authors[1])}"
    else:
        label = f"{_surname(ref.authors[0])} et al."
    return f'({label}, {year})'


def _mla_inline(ref: Reference) -> str:
    """MLA uses (Author Page) format inline."""
    if not ref.authors:
        label = ref.title[:20] if ref.title else 'Anon'
    else:
        label = _surname(ref.authors[0])
    return f'({label})'


def _chicago_inline(ref: Reference) -> str:
    """Chicago author-date uses (Author Year) format."""
    year = ref.year or 'n.d.'
    if not ref.authors:
        label = ref.title[:20] if ref.title else 'Anon'
    elif len(ref.authors) == 1:
        label = _surname(ref.authors[0])
    elif len(ref.authors) == 2:
        label = f"{_surname(ref.authors[0])} and {_surname(ref.authors[1])}"
    else:
        label = f"{_surname(ref.authors[0])} et al."
    return f'({label} {year})'


_SUPER = str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹')


def _to_superscript(s: str) -> str:
    return s.translate(_SUPER)


# ─── Surname / initials helpers ───────────────────────────────────────────────

def _is_initials(tok: str) -> bool:
    """True if token looks like initials: 1-3 uppercase letters, optionally dotted."""
    return bool(re.fullmatch(r'[A-Z]{1,3}\.?', tok))


def _surname(author: str) -> str:
    """Extract surname from any common author format."""
    author = author.strip().rstrip('.,')
    # "Smith, John" → "Smith"
    if ',' in author:
        return author.split(',')[0].strip()
    parts = author.split()
    if not parts:
        return author
    # "Smith J" or "Smith JK" → surname is first token
    if len(parts) >= 2 and _is_initials(parts[-1]):
        return parts[0]
    # "John Smith" → "Smith"
    return parts[-1]


def _make_initials(name_or_parts) -> str:
    """'John Paul' or ['John', 'Paul'] → 'J. P.'"""
    if isinstance(name_or_parts, str):
        name_or_parts = name_or_parts.split()
    return ' '.join(p[0].upper() + '.' for p in name_or_parts if p)


def _normalise_author(author: str):
    """
    Return (surname, initials_str) for any input format.
    Handles: "Smith J", "Smith, John", "John Smith", "Smith JK"
    """
    author = author.strip().rstrip('.,')
    if ',' in author:
        surname, rest = author.split(',', 1)
        initials = _make_initials(rest.strip())
        return surname.strip(), initials
    parts = author.split()
    if not parts:
        return author, ''
    if len(parts) >= 2 and _is_initials(parts[-1]):
        # "Smith J" format
        return parts[0], _make_initials(parts[1:])
    if len(parts) == 1:
        return parts[0], ''
    # "John Smith" format
    surname = parts[-1]
    initials = _make_initials(parts[:-1])
    return surname, initials


# ─── Bibliography formatters ──────────────────────────────────────────────────

def format_bibliography(refs: List[Reference], style: str) -> str:
    """Format the complete bibliography section for the given style."""
    style = style.lower()
    lines = ['References\n' + '=' * 60]
    for ref in refs:
        lines.append(_format_entry(ref, style))
    return '\n\n'.join(lines)


def _format_entry(ref: Reference, style: str) -> str:
    if style == 'apa':       return _apa_entry(ref)
    if style == 'vancouver': return _vancouver_entry(ref)
    if style == 'ieee':      return _ieee_entry(ref)
    if style == 'nature':    return _nature_entry(ref)
    if style == 'mla':       return _mla_entry(ref)
    if style == 'chicago':   return _chicago_entry(ref)
    if style == 'harvard':   return _harvard_entry(ref)
    if style == 'ama':       return _ama_entry(ref)
    return f'{ref.index}. {ref.raw}'


# ── APA ───────────────────────────────────────────────────────────────────────
def _apa_entry(ref: Reference) -> str:
    parts = []
    if ref.authors:
        parts.append(_apa_author_list(ref.authors))
    parts.append(f'({ref.year or "n.d."}).')
    if ref.title:
        parts.append(f'{ref.title}.')
    j = _journal_block(ref)
    if j:
        parts.append(j)
    if ref.doi:
        parts.append(ref.doi)
    result = ' '.join(parts)
    result = re.sub(r'\.{2,}', '.', result)   # collapse double periods
    return result


def _apa_author_list(authors: List[str]) -> str:
    fmt = []
    for a in authors:
        surname, inits = _normalise_author(a)
        fmt.append(f'{surname}, {inits}' if inits else surname)
    if len(fmt) > 20:
        return ', '.join(fmt[:19]) + ', ... ' + fmt[-1] + '.'
    if len(fmt) == 1:
        return fmt[0] + '.'
    return ', '.join(fmt[:-1]) + ', & ' + fmt[-1] + '.'


# ── Vancouver ─────────────────────────────────────────────────────────────────
def _vancouver_entry(ref: Reference) -> str:
    parts = [f'{ref.index}.']
    if ref.authors:
        parts.append(_vancouver_author_list(ref.authors))
    if ref.title:
        parts.append(f'{ref.title}.')
    j = _journal_block(ref)
    if j:
        parts.append(j)
    if ref.doi:
        parts.append(ref.doi)
    return ' '.join(parts)


def _vancouver_author_list(authors: List[str]) -> str:
    fmt = []
    for a in authors[:6]:
        surname, inits = _normalise_author(a)
        inits_no_dots = inits.replace('.', '').replace(' ', '')
        fmt.append(f'{surname} {inits_no_dots}' if inits_no_dots else surname)
    result = ', '.join(fmt)
    if len(authors) > 6:
        result += ', et al.'
    return result + '.'


# ── IEEE ──────────────────────────────────────────────────────────────────────
def _ieee_entry(ref: Reference) -> str:
    parts = [f'[{ref.index}]']
    if ref.authors:
        parts.append(_ieee_author_list(ref.authors))
    if ref.title:
        parts.append(f'"{ref.title},"')
    if ref.journal:
        parts.append(f'{ref.journal},')
    if ref.volume:
        v = f'vol. {ref.volume}'
        if ref.issue:
            v += f', no. {ref.issue}'
        parts.append(v + ',')
    if ref.pages:
        parts.append(f'pp. {ref.pages},')
    if ref.year:
        parts.append(f'{ref.year}.')
    if ref.doi:
        parts.append(ref.doi + '.')
    return ' '.join(parts)


def _ieee_author_list(authors: List[str]) -> str:
    fmt = []
    for a in authors:
        surname, inits = _normalise_author(a)
        fmt.append(f'{inits} {surname}' if inits else surname)
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
        parts.append(ref.doi)
    return ' '.join(parts)


def _nature_author_list(authors: List[str]) -> str:
    fmt = []
    for a in authors[:10]:
        surname, inits = _normalise_author(a)
        inits_dotted = (
            '.'.join(c for c in inits.replace(' ', '').replace('.', '')) + '.'
            if inits else ''
        )
        fmt.append(f'{surname}, {inits_dotted}' if inits_dotted else surname)
    result = ', '.join(fmt)
    if len(authors) > 10:
        result += ' et al.'
    return result


# ── MLA ───────────────────────────────────────────────────────────────────────
def _mla_entry(ref: Reference) -> str:
    """MLA 9th edition format."""
    parts = []
    if ref.authors:
        parts.append(_mla_author_list(ref.authors))
    if ref.title:
        parts.append(f'"{ref.title}."')
    if ref.journal:
        parts.append(f'*{ref.journal}*,')
    if ref.volume:
        v = f'vol. {ref.volume}'
        if ref.issue:
            v += f', no. {ref.issue}'
        parts.append(v + ',')
    if ref.year:
        parts.append(f'{ref.year},')
    if ref.pages:
        parts.append(f'pp. {ref.pages}.')
    if ref.doi:
        parts.append(ref.doi)
    return ' '.join(parts)


def _mla_author_list(authors: List[str]) -> str:
    if not authors:
        return ''
    surname0, inits0 = _normalise_author(authors[0])
    first = f'{surname0}, {inits0}' if inits0 else surname0
    if len(authors) == 1:
        return first + '.'
    if len(authors) > 3:
        return first + ', et al.'
    rest = []
    for a in authors[1:]:
        surname, inits = _normalise_author(a)
        rest.append(f'{inits} {surname}' if inits else surname)
    return first + ', and ' + ', and '.join(rest) + '.'


# ── Chicago ───────────────────────────────────────────────────────────────────
def _chicago_entry(ref: Reference) -> str:
    """Chicago author-date (17th ed.) format."""
    parts = []
    if ref.authors:
        parts.append(_chicago_author_list(ref.authors))
    if ref.year:
        parts.append(f'{ref.year}.')
    if ref.title:
        parts.append(f'"{ref.title}."')
    if ref.journal:
        parts.append(f'*{ref.journal}*')
    if ref.volume:
        v = ref.volume
        if ref.issue:
            v += f' ({ref.issue})'
        parts.append(v + ':')
    if ref.pages:
        parts.append(f'{ref.pages}.')
    if ref.doi:
        parts.append(ref.doi)
    return ' '.join(parts)


def _chicago_author_list(authors: List[str]) -> str:
    if not authors:
        return ''
    surname0, inits0 = _normalise_author(authors[0])
    first = f'{surname0}, {inits0}' if inits0 else surname0
    if len(authors) == 1:
        return first + '.'
    rest = []
    for a in authors[1:]:
        surname, inits = _normalise_author(a)
        rest.append(f'{inits} {surname}' if inits else surname)
    if len(authors) <= 3:
        return first + ', and ' + ', and '.join(rest) + '.'
    return first + ', et al.'


# ─── Shared helper ────────────────────────────────────────────────────────────
def _journal_block(ref: Reference) -> str:
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


# ── Harvard ────────────────────────────────────────────────────────────────────────

def _harvard_inline(ref: Reference) -> str:
    """
    Harvard author-date inline: (Smith, 2020) / (Smith and Jones, 2020) /
    (Smith et al., 2020)
    """
    year = ref.year or 'n.d.'
    if not ref.authors:
        label = ref.title[:20] if ref.title else 'Anon'
    elif len(ref.authors) == 1:
        label = _surname(ref.authors[0])
    elif len(ref.authors) == 2:
        label = f"{_surname(ref.authors[0])} and {_surname(ref.authors[1])}"
    else:
        label = f"{_surname(ref.authors[0])} et al."
    return f'({label}, {year})'


def _harvard_entry(ref: Reference) -> str:
    """
    Harvard reference list format:
    Smith, J. and Jones, A. (2020) 'Title of article', *Journal Name*,
    vol. 10, no. 2, pp. 1-5.
    """
    parts = []
    if ref.authors:
        parts.append(_harvard_author_list(ref.authors))
    if ref.year:
        parts.append(f'({ref.year})')
    if ref.title:
        parts.append(f"\u2018{ref.title}\u2019,")
    if ref.journal:
        parts.append(f'{ref.journal},')
    if ref.volume:
        parts.append(f'vol. {ref.volume},')
    if ref.issue:
        parts.append(f'no. {ref.issue},')
    if ref.pages:
        parts.append(f'pp. {ref.pages}.')
    if ref.doi:
        parts.append(ref.doi)
    result = ' '.join(parts)
    return re.sub(r',\s*\.', '.', result)   # clean trailing comma-period


def _harvard_author_list(authors: list) -> str:
    """Harvard: Smith, J. and Jones, A. and Brown, B. (up to 3), et al. beyond."""
    fmt = []
    for a in authors[:3]:
        surname, inits = _normalise_author(a)
        fmt.append(f'{surname}, {inits}' if inits else surname)
    result = ' and '.join(fmt)
    if len(authors) > 3:
        result += ' et al.'
    return result


# ── AMA (American Medical Association) ────────────────────────────────────────────

def _ama_entry(ref: Reference) -> str:
    """
    AMA 11th edition:
    1. Smith JK, Jones AL, Brown BC. Title of article. *Journal Name*.
       Year;vol(issue):pages. doi:10.xxxx/yyy
    """
    parts = [f'{ref.index}.']
    if ref.authors:
        parts.append(_ama_author_list(ref.authors))
    if ref.title:
        parts.append(f'{ref.title}.')
    if ref.journal:
        parts.append(f'{ref.journal}.')
    viy = []
    if ref.year:
        viy.append(ref.year)
    if ref.volume:
        v = ref.volume
        if ref.issue:
            v += f'({ref.issue})'
        viy.append(v)
    if ref.pages:
        viy.append(ref.pages)
    if viy:
        # Format: Year;vol(issue):pages
        if len(viy) == 3:
            parts.append(f'{viy[0]};{viy[1]}:{viy[2]}.')
        elif len(viy) == 2:
            parts.append(f'{viy[0]};{viy[1]}.')
        else:
            parts.append(viy[0] + '.')
    if ref.doi:
        parts.append(f'doi:{ref.doi.replace("https://doi.org/", "")}')
    return ' '.join(parts)


def _ama_author_list(authors: list) -> str:
    """
    AMA: Smith JK, Jones AL. Up to 6 authors, then et al.
    No periods after initials.
    """
    fmt = []
    for a in authors[:6]:
        surname, inits = _normalise_author(a)
        # AMA uses no spaces or dots: "Smith JK"
        inits_nodot = inits.replace('.', '').replace(' ', '')
        fmt.append(f'{surname} {inits_nodot}' if inits_nodot else surname)
    result = ', '.join(fmt)
    if len(authors) > 6:
        result += ', et al.'
    return result + '.'
