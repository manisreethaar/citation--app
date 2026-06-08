"""
v2/bridge.py  –  Clean interface between v2 pipeline and the Flask app
======================================================================

Provides two public functions:
  process_v2(text, style)  → PipelineResult (or raises ValueError/RuntimeError)
  preview_v2(text)         → dict with refs, detection, sentences, coverage

Also patches style_engine at import time to add the 4 missing styles.
"""

import sys
import os

# Make v2 importable regardless of working directory
_V2_DIR = os.path.dirname(os.path.abspath(__file__))
if _V2_DIR not in sys.path:
    sys.path.insert(0, _V2_DIR)

# ── Patch style_engine with missing styles BEFORE any pipeline import ──────────
try:
    import style_engine as _se
    from style_engine_ext import (
        harvard_inline, harvard_entry,
        ama_inline,     ama_entry,
        mla_inline,     mla_entry,
        chicago_inline, chicago_entry,
    )

    # Extend SUPPORTED_STYLES
    for s in ('harvard', 'ama', 'mla', 'chicago'):
        if s not in _se.SUPPORTED_STYLES:
            _se.SUPPORTED_STYLES.append(s)

    # Patch inline_marker
    _orig_inline = _se.inline_marker
    def _patched_inline(ref, style):
        style = style.lower()
        if style == 'harvard': return harvard_inline(ref)
        if style == 'ama':     return ama_inline(ref)
        if style == 'mla':     return mla_inline(ref)
        if style == 'chicago': return chicago_inline(ref)
        return _orig_inline(ref, style)
    _se.inline_marker = _patched_inline

    # Patch format_entry
    _orig_entry = _se.format_entry
    def _patched_entry(ref, style):
        style = style.lower()
        if style == 'harvard': return harvard_entry(ref)
        if style == 'ama':     return ama_entry(ref)
        if style == 'mla':     return mla_entry(ref)
        if style == 'chicago': return chicago_entry(ref)
        return _orig_entry(ref, style)
    _se.format_entry = _patched_entry

    _STYLES_PATCHED = True
except Exception as _patch_err:
    _STYLES_PATCHED = False
    print(f'[v2.bridge] Style patch failed: {_patch_err}')

# ── Core imports ───────────────────────────────────────────────────────────────
from pipeline import run_pipeline, PipelineResult
from document_model import parse_document, SectionType, SentenceRole
from reference_model import (
    parse_reference_section, split_body_and_references, Reference
)
from scoring_engine import (
    score_document, best_matches_per_ref, THRESHOLD_AUTO, THRESHOLD_REVIEW
)
from citation_inventory import build_citation_inventory
from coverage_audit import audit_coverage

SUPPORTED_STYLES_V2 = [
    'apa', 'vancouver', 'ieee', 'nature',
    'harvard', 'ama', 'mla', 'chicago'
]


def process_v2(text: str, style: str = 'apa',
               print_report: bool = False) -> PipelineResult:
    """
    Run the full v2 pipeline on document text.
    Raises ValueError if no references found.
    Raises RuntimeError on other failures.
    """
    style = style.lower()
    if style not in SUPPORTED_STYLES_V2:
        raise ValueError(
            f"Style '{style}' not supported. Choose from: {SUPPORTED_STYLES_V2}"
        )
    return run_pipeline(text, style=style, print_report=print_report)


def preview_v2(text: str) -> dict:
    """
    Analyse document WITHOUT writing output. Returns structured preview data:
    {
      refs: [{index, authors, year, title, journal, ref_type, confidence,
              cited, signals, claim_type, domain}],
      total: int,
      body_words: int,
      detection: {mode, count, style_guess, description, examples},
      sections: [{name, type, sentence_count}],
      review_candidates: [{sentence, ref_index, score, reason}],
    }
    """
    body_text, ref_section_text = split_body_and_references(text)

    if not ref_section_text.strip():
        raise ValueError('No reference section found in document.')

    refs = parse_reference_section(ref_section_text)
    if not refs:
        raise ValueError('Could not parse any references.')

    # Detect existing citation mode
    from citation_detector import detect_citation_mode, extract_cited_numbers
    detection = detect_citation_mode(body_text)
    cited_nums = set(extract_cited_numbers(body_text)) \
        if detection['mode'] == 'numbered' else set()

    # Build citation inventory from existing markers
    inventory = build_citation_inventory(body_text, refs)

    # Parse document structure
    from citation_inventory import strip_existing_citations
    clean_body = strip_existing_citations(body_text, inventory)
    doc = parse_document(clean_body)
    sentences = doc.body_sentences

    # Build sentence inventory (which refs already cited near which sentence)
    from citation_inventory import build_sentence_inventory
    sent_inventory = build_sentence_inventory(inventory, sentences)

    # Score all pairs
    all_matches = score_document(sentences, refs, sent_inventory)
    by_ref = best_matches_per_ref(all_matches)

    # Compute per-ref confidence
    ref_list = []
    for ref in refs:
        matches = by_ref.get(ref.index, [])
        best_score = matches[0].score if matches else 0.0

        # For numbered docs: confidence = whether [n] found in body
        if detection['mode'] == 'numbered':
            is_cited   = ref.index in cited_nums
            confidence = 95 if is_cited else 0
        elif detection['mode'] == 'superscript':
            is_cited   = True
            confidence = 80
        else:
            confidence = int(best_score * 100)
            is_cited   = best_score >= THRESHOLD_REVIEW

        # Get signals from best match if available
        signals = {}
        if matches:
            m = matches[0]
            signals = {k: round(v, 3) for k, v in m.signals.items()}

        ref_list.append({
            'index':      ref.index,
            'authors':    [str(a) for a in ref.authors[:3]],
            'year':       ref.year,
            'title':      ref.title,
            'journal':    ref.journal,
            'ref_type':   ref.claim_type.value if hasattr(ref.claim_type, 'value') else 'article',
            'domain':     ref.domain.value if hasattr(ref.domain, 'value') else 'unknown',
            'confidence': confidence,
            'cited':      is_cited,
            'signals':    signals,
        })

    # Section summary
    sections = []
    for sec in doc.sections:
        if sec.section_type.value != 'references':
            sections.append({
                'name':           sec.name,
                'type':           sec.section_type.value,
                'sentence_count': len(sec.sentences),
            })

    # Review candidates (medium confidence: needs_review but not auto)
    review_candidates = []
    for m in all_matches:
        if m.needs_review and not m.auto:
            review_candidates.append({
                'sentence':  m.sentence.text[:120],
                'section':   m.sentence.section_type.value,
                'ref_index': m.reference.index,
                'score':     round(m.score, 3),
                'signals':   {k: round(v, 3) for k, v in m.signals.items()},
            })
    # Sort by score desc, cap at 20
    review_candidates.sort(key=lambda x: x['score'], reverse=True)
    review_candidates = review_candidates[:20]

    return {
        'refs':              ref_list,
        'total':             len(refs),
        'body_words':        len(body_text.split()),
        'detection':         detection,
        'sections':          sections,
        'review_candidates': review_candidates,
    }
