"""
tests/test_citation_styles.py  –  Unit tests for citation_styles module.
Run with: python -m pytest tests/ -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from reference_parser import Reference
from citation_styles import (
    inline_citation, format_bibliography,
    _surname, _normalise_author, _is_initials
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def make_ref(index=1, authors=None, year='2020', title='Test Title',
             journal='Nature', volume='10', pages='1-5', doi=None):
    ref = Reference(
        raw='raw',
        index=index,
        authors=authors or ['Smith, John', 'Jones, Alice'],
        year=year,
        title=title,
        journal=journal,
        volume=volume,
        pages=pages,
        doi=doi,
    )
    return ref


# ── _is_initials ──────────────────────────────────────────────────────────────

def test_is_initials_single():
    assert _is_initials('J') is True

def test_is_initials_double():
    assert _is_initials('JK') is True

def test_is_initials_with_dot():
    assert _is_initials('J.') is True

def test_is_initials_full_name():
    assert _is_initials('John') is False

def test_is_initials_lowercase():
    assert _is_initials('jk') is False


# ── _surname ──────────────────────────────────────────────────────────────────

def test_surname_comma_format():
    assert _surname('Smith, John') == 'Smith'

def test_surname_firstname_lastname():
    assert _surname('John Smith') == 'Smith'

def test_surname_initials_format():
    assert _surname('Smith J') == 'Smith'

def test_surname_initials_dotted():
    assert _surname('Smith J.') == 'Smith'

def test_surname_single_name():
    assert _surname('Smith') == 'Smith'


# ── _normalise_author ─────────────────────────────────────────────────────────

def test_normalise_comma_format():
    surname, inits = _normalise_author('Smith, John')
    assert surname == 'Smith'
    assert inits == 'J.'

def test_normalise_initials_format():
    surname, inits = _normalise_author('Smith JK')
    assert surname == 'Smith'

def test_normalise_full_name():
    surname, inits = _normalise_author('John Smith')
    assert surname == 'Smith'
    assert 'J' in inits


# ── inline_citation ───────────────────────────────────────────────────────────

def test_apa_inline_multiple_authors():
    ref = make_ref(authors=['Smith, J', 'Jones, A', 'Brown, B'])
    result = inline_citation(ref, 'apa')
    assert result == '(Smith et al., 2020)'

def test_apa_inline_single_author():
    ref = make_ref(authors=['Smith, J'])
    result = inline_citation(ref, 'apa')
    assert 'Smith' in result
    assert '2020' in result

def test_apa_inline_two_authors():
    ref = make_ref(authors=['Smith, J', 'Jones, A'])
    result = inline_citation(ref, 'apa')
    assert '&' in result
    assert 'Smith' in result
    assert 'Jones' in result

def test_apa_inline_no_year():
    ref = make_ref(year=None, authors=['Smith, J'])
    assert 'n.d.' in inline_citation(ref, 'apa')

def test_vancouver_inline():
    ref = make_ref(index=3)
    assert inline_citation(ref, 'vancouver') == '[3]'

def test_ieee_inline():
    ref = make_ref(index=7)
    assert inline_citation(ref, 'ieee') == '[7]'

def test_nature_inline():
    ref = make_ref(index=2)
    assert inline_citation(ref, 'nature') == '[2]'

def test_nature_superscript():
    ref = make_ref(index=2)
    result = inline_citation(ref, 'nature', superscript=True)
    assert result == '²'

def test_mla_inline():
    ref = make_ref(authors=['Smith, J'])
    result = inline_citation(ref, 'mla')
    assert 'Smith' in result

def test_chicago_inline():
    ref = make_ref(authors=['Smith, J'])
    result = inline_citation(ref, 'chicago')
    assert 'Smith' in result
    assert '2020' in result

def test_unknown_style_raises():
    ref = make_ref()
    with pytest.raises(ValueError):
        inline_citation(ref, 'harvard')


# ── format_bibliography ───────────────────────────────────────────────────────

def test_bibliography_contains_all_refs():
    refs = [make_ref(index=i, authors=[f'Author{i}, X']) for i in range(1, 4)]
    bib = format_bibliography(refs, 'apa')
    for i in range(1, 4):
        assert f'Author{i}' in bib

@pytest.mark.parametrize('style', ['apa', 'vancouver', 'ieee', 'nature', 'mla', 'chicago'])
def test_bibliography_all_styles(style):
    refs = [make_ref()]
    bib = format_bibliography(refs, style)
    assert 'Smith' in bib or 'Test Title' in bib


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_apa_no_authors():
    ref = Reference(raw='raw', index=1, year='2020', journal='Nature')
    result = inline_citation(ref, 'apa')
    assert 'Nature' in result or 'Anon' in result

def test_apa_entry_double_period():
    """Double periods should be collapsed in APA entries."""
    ref = make_ref(title='A study.')
    from citation_styles import _apa_entry
    entry = _apa_entry(ref)
    assert '..' not in entry
