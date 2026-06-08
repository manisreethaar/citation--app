"""
tests/test_reference_parser.py  –  Unit tests for reference_parser module.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from reference_parser import (
    split_references_from_body,
    parse_references,
    parse_authors,
    Reference,
)


SAMPLE_DOC = """
This is the body of the paper. Smith et al. (2020) found that something
is true. Jones (2019) also confirmed this.

References
Smith, J., Jones, A., & Brown, B. (2020). A great study. Journal of Science, 10, 1-5.
Jones, A. (2019). Another paper. Nature, 5, 10-15.
"""


def test_split_references_from_body():
    body, refs = split_references_from_body(SAMPLE_DOC)
    assert 'Smith et al.' in body
    assert 'Smith, J.' in refs


def test_split_empty_doc():
    body, refs = split_references_from_body("no references here")
    assert body == "no references here"
    assert refs == ''


def test_split_bibliography_header():
    doc = "body text\n\nBibliography\nSmith J (2020). Title. Journal."
    body, refs = split_references_from_body(doc)
    assert 'body text' in body
    assert 'Smith' in refs


def test_parse_references_basic():
    ref_text = "Smith, J. (2020). Great paper. Journal of X, 10, 1-5."
    refs = parse_references(ref_text)
    assert len(refs) >= 1
    ref = refs[0]
    assert ref.year == '2020'


def test_parse_references_numbered():
    ref_text = "[1] Smith J (2020). A title. Nature, 5, 100-105.\n[2] Jones A (2019). Another. Science, 3, 10-20."
    refs = parse_references(ref_text)
    assert len(refs) == 2


def test_reference_first_author_surname():
    ref_text = "Smith, John. (2020). Title. Journal, 1, 1-5."
    refs = parse_references(ref_text)
    if refs:
        assert refs[0].first_author_surname == 'Smith'


def test_parse_authors_semicolon():
    authors = parse_authors("Smith J; Jones A; Brown B")
    assert len(authors) >= 2


def test_parse_authors_and_separator():
    authors = parse_authors("Smith J and Jones A")
    assert any('Smith' in a for a in authors)
    assert any('Jones' in a for a in authors)


def test_parse_references_from_sample():
    _, ref_section = split_references_from_body(SAMPLE_DOC)
    refs = parse_references(ref_section)
    assert len(refs) >= 1
    surnames = [r.first_author_surname for r in refs if r.first_author_surname]
    assert 'Smith' in surnames or 'Jones' in surnames
