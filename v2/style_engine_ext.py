"""
v2/style_engine_ext.py  –  Extension styles for v2 style engine
Adds: Harvard, AMA, MLA, Chicago to the 4 already in style_engine.py
Imported by style_engine.py via patching OR used directly.
"""

import re
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from reference_model import Reference, Author
from typing import List


# ── Harvard ────────────────────────────────────────────────────────────────────

def harvard_inline(ref: Reference) -> str:
    year = ref.year or 'n.d.'
    authors = ref.authors
    if not authors:
        label = ref.journal or ref.title or 'Anon'
    elif len(authors) == 1:
        label = authors[0].surname
    elif len(authors) == 2:
        label = f"{authors[0].surname} and {authors[1].surname}"
    else:
        label = f"{authors[0].surname} et al."
    return f'({label}, {year})'


def harvard_entry(ref: Reference) -> str:
    parts = []
    if ref.authors:
        surnames = [a.surname for a in ref.authors]
        if len(surnames) == 1:
            parts.append(surnames[0] + ',')
        elif len(surnames) == 2:
            parts.append(surnames[0] + ' and ' + surnames[1] + ',')
        else:
            parts.append(', '.join(surnames[:-1]) + ' and ' + surnames[-1] + ',')

    parts.append(f'({ref.year or "n.d."}).')

    if ref.title:
        parts.append(f"'{ref.title}',")

    if ref.journal:
        jpart = ref.journal
        if ref.volume:
            jpart += f', {ref.volume}'
            if ref.issue:
                jpart += f'({ref.issue})'
        if ref.pages:
            jpart += f', pp. {ref.pages}'
        parts.append(jpart + '.')

    if ref.doi:
        doi = ref.doi if ref.doi.startswith('http') else f'https://doi.org/{ref.doi}'
        parts.append(f'Available at: {doi}')

    return ' '.join(parts)


# ── AMA ────────────────────────────────────────────────────────────────────────

def ama_inline(ref: Reference) -> str:
    # AMA uses superscript numbers
    _SUP = str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹')
    return str(ref.index).translate(_SUP)


def ama_entry(ref: Reference) -> str:
    parts = [f'{ref.index}.']

    if ref.authors:
        fmt = []
        for a in ref.authors[:6]:
            inits = a.initials.replace('.', '').replace(' ', '')
            fmt.append(f'{a.surname} {inits}' if inits else a.surname)
        result = ', '.join(fmt)
        if len(ref.authors) > 6:
            result += ', et al'
        parts.append(result + '.')

    if ref.title:
        parts.append(f'{ref.title}.')

    if ref.journal:
        jpart = ref.journal + '.'
        if ref.year:
            jpart += f' {ref.year}'
        if ref.volume:
            jpart += f';{ref.volume}'
            if ref.issue:
                jpart += f'({ref.issue})'
        if ref.pages:
            jpart += f':{ref.pages}'
        jpart += '.'
        parts.append(jpart)

    if ref.doi:
        doi = ref.doi if ref.doi.startswith('http') else f'https://doi.org/{ref.doi}'
        parts.append(f'doi:{doi}')

    return ' '.join(parts)


# ── MLA 9th ────────────────────────────────────────────────────────────────────

def mla_inline(ref: Reference) -> str:
    # MLA uses (Author page) — no page tracking, so just author
    if not ref.authors:
        return f'({ref.title[:20] if ref.title else "Anon"})'
    surname = ref.authors[0].surname
    if len(ref.authors) > 1:
        return f'({surname} et al.)'
    return f'({surname})'


def mla_entry(ref: Reference) -> str:
    parts = []

    if ref.authors:
        fmt = []
        for i, a in enumerate(ref.authors):
            if i == 0:
                # First author: Surname, Firstname
                fmt.append(a.surname + (f', {a.initials}' if a.initials else ''))
            else:
                fmt.append((a.initials + ' ' if a.initials else '') + a.surname)
        if len(fmt) > 3:
            parts.append(fmt[0] + ', et al.')
        else:
            parts.append(', and '.join(fmt) + '.')

    if ref.title:
        parts.append(f'"{ref.title}."')

    if ref.journal:
        jpart = f'{ref.journal},'
        if ref.volume:
            jpart += f' vol. {ref.volume},'
            if ref.issue:
                jpart += f' no. {ref.issue},'
        if ref.year:
            jpart += f' {ref.year},'
        if ref.pages:
            jpart += f' pp. {ref.pages}.'
        parts.append(jpart)

    if ref.doi:
        doi = ref.doi if ref.doi.startswith('http') else f'https://doi.org/{ref.doi}'
        parts.append(doi)

    return ' '.join(parts)


# ── Chicago 17th (author-date) ─────────────────────────────────────────────────

def chicago_inline(ref: Reference) -> str:
    year = ref.year or 'n.d.'
    if not ref.authors:
        label = ref.title[:20] if ref.title else 'Anon'
    elif len(ref.authors) == 1:
        label = ref.authors[0].surname
    elif len(ref.authors) == 2:
        label = f"{ref.authors[0].surname} and {ref.authors[1].surname}"
    else:
        label = f"{ref.authors[0].surname} et al."
    return f'({label} {year})'


def chicago_entry(ref: Reference) -> str:
    parts = []

    if ref.authors:
        fmt = []
        for i, a in enumerate(ref.authors):
            if i == 0:
                fmt.append(a.surname + (f', {a.initials}' if a.initials else ''))
            else:
                fmt.append((a.initials + ' ' if a.initials else '') + a.surname)
        if len(fmt) > 10:
            parts.append(fmt[0] + ', et al.')
        else:
            sep = ', and ' if len(fmt) > 2 else ' and '
            parts.append(sep.join(fmt[::-1][:1] + [', '.join(fmt[:-1])]) + '.')
            # simpler:
            parts.clear()
            parts.append(', '.join(fmt[:-1]) + (', and ' if len(fmt) > 1 else '') +
                         (fmt[-1] if len(fmt) > 1 else fmt[0]) + '.')

    parts.append(f'{ref.year or "n.d."}.')

    if ref.title:
        parts.append(f'"{ref.title}."')

    if ref.journal:
        jpart = f'{ref.journal}'
        if ref.volume:
            jpart += f' {ref.volume}'
            if ref.issue:
                jpart += f', no. {ref.issue}'
        if ref.year:
            jpart += f' ({ref.year})'
        if ref.pages:
            jpart += f': {ref.pages}'
        parts.append(jpart + '.')

    if ref.doi:
        doi = ref.doi if ref.doi.startswith('http') else f'https://doi.org/{ref.doi}'
        parts.append(f'https://doi.org/{doi}.')

    return ' '.join(parts)
