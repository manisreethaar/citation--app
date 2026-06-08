"""
pipeline.py
============
The main orchestration engine. Runs all stages in correct order.

Stage 0 — Citation inventory: detect + resolve existing markers, strip them
Stage 1 — Document parsing: structure, sentences, roles
Stage 2 — Reference parsing: rich representation
Stage 3 — Scoring: multi-signal relevance scoring
Stage 4 — Insertion: confirmed matches only, right-to-left, clean
Stage 5 — Coverage audit: report uncited refs + review candidates
Stage 6 — Output: write cited document in target style
"""

import re
from typing import List, Dict, Tuple, Optional
from pathlib import Path

from document_model import parse_document, SectionType, SentenceRole
from reference_model import parse_reference_section, split_body_and_references, Reference
from citation_inventory import (
    build_citation_inventory, strip_existing_citations,
    build_sentence_inventory
)
from scoring_engine import (
    score_document, best_matches_per_ref, THRESHOLD_AUTO
)
from coverage_audit import audit_coverage
from style_engine import inline_marker, format_bibliography, SUPPORTED_STYLES


# ─── Result object ────────────────────────────────────────────────────────────

class PipelineResult:
    def __init__(self):
        self.cited_body: str = ''
        self.bibliography: str = ''
        self.full_text: str = ''
        self.coverage_report = None
        self.refs: List[Reference] = []
        self.num_inserted: int = 0
        self.num_refs: int = 0


# ─── Main pipeline ────────────────────────────────────────────────────────────

def run_pipeline(text: str, style: str = 'apa',
                 print_report: bool = False) -> PipelineResult:

    style = style.lower()
    if style not in SUPPORTED_STYLES:
        raise ValueError(f"Style '{style}' not in {SUPPORTED_STYLES}")

    result = PipelineResult()

    # ── Stage 0: Split body + references ─────────────────────────────────────
    body_text, ref_section_text = split_body_and_references(text)

    if not ref_section_text.strip():
        raise ValueError(
            "No reference section found. Ensure your document has a "
            "'References' heading before the reference list."
        )

    # ── Stage 1: Parse references ─────────────────────────────────────────────
    refs = parse_reference_section(ref_section_text)
    if not refs:
        raise ValueError("Could not parse any references from the reference section.")

    result.refs = refs
    result.num_refs = len(refs)

    # ── Stage 0b: Citation inventory — detect & strip existing markers ────────
    inventory = build_citation_inventory(body_text, refs)
    clean_body = strip_existing_citations(body_text, inventory)

    # ── Stage 2: Parse document structure ─────────────────────────────────────
    doc = parse_document(clean_body)
    sentences = doc.body_sentences

    # Build sentence → already-cited-refs mapping (from inventory)
    sent_inventory = build_sentence_inventory(inventory, sentences)

    # ── Stage 3: Score all (sentence × reference) pairs ───────────────────────
    all_matches = score_document(sentences, refs, sent_inventory)

    # ── Stage 4: Select confirmed matches (score >= THRESHOLD_AUTO) ───────────
    confirmed = [m for m in all_matches if m.auto]

    # Track which refs got auto-confirmed
    confirmed_ref_indices: Dict[int, bool] = {}
    for m in confirmed:
        confirmed_ref_indices[m.reference.index] = True

    # ── Stage 5: Coverage audit ───────────────────────────────────────────────
    report = audit_coverage(refs, all_matches, confirmed_ref_indices)
    result.coverage_report = report

    if print_report:
        print(report.summary())

    # ── Stage 6: Insert citations into clean body text ────────────────────────
    # Group confirmed matches by sentence — one sentence may cite multiple refs
    by_sentence: Dict[int, List] = {}
    for m in confirmed:
        by_sentence.setdefault(m.sentence.index, []).append(m)

    # Build insertion map: char_end_of_sentence → citation string
    # We insert citations at the END of the sentence they belong to
    insertions: List[Tuple[int, str]] = []
    for sent_idx, matches in by_sentence.items():
        sent = matches[0].sentence
        # Sort refs within this sentence by index for consistent ordering
        sorted_refs = sorted(matches, key=lambda m: m.reference.index)
        # Build combined citation string
        if style == 'apa':
            # APA: separate citations for each ref
            cite_str = ' '.join(inline_marker(m.reference, style) for m in sorted_refs)
        else:
            # Numbered styles: [1,2,3] grouped or separate
            markers = [inline_marker(m.reference, style) for m in sorted_refs]
            cite_str = ' '.join(markers)

        # Insert position: right before the sentence-ending punctuation
        text_pos = sent.char_end
        insertions.append((text_pos, ' ' + cite_str))

    # Apply insertions right-to-left (highest char position first)
    cited_body = clean_body
    for pos, cite_str in sorted(insertions, key=lambda x: x[0], reverse=True):
        cited_body = cited_body[:pos] + cite_str + cited_body[pos:]

    result.cited_body = cited_body
    result.num_inserted = len(insertions)

    # ── Stage 7: Format bibliography ──────────────────────────────────────────
    result.bibliography = format_bibliography(refs, style)

    # ── Assemble final document ───────────────────────────────────────────────
    result.full_text = cited_body.rstrip() + '\n\n' + result.bibliography

    return result


# ─── File-level entry point ───────────────────────────────────────────────────

def process_file(input_path: str, style: str = 'apa',
                 output_path: str = None,
                 print_report: bool = False) -> str:
    """
    Read a file, run pipeline, write output. Returns output path.
    Supports .docx, .pdf, .txt
    """
    from file_io import read_file, write_file

    ext = Path(input_path).suffix.lower()

    if output_path is None:
        stem = Path(input_path).stem
        output_path = str(Path(input_path).parent / f"{stem}_cited{ext}")

    print(f"[auto-citer v2] Reading  : {input_path}")
    print(f"[auto-citer v2] Style    : {style.upper()}")

    text = read_file(input_path)
    result = run_pipeline(text, style, print_report)

    print(f"[auto-citer v2] Refs found    : {result.num_refs}")
    print(f"[auto-citer v2] Citations added: {result.num_inserted}")
    print(f"[auto-citer v2] Uncited refs  : {len(result.coverage_report.uncited)}")

    write_file(result.full_text, output_path, original_path=input_path)
    print(f"[auto-citer v2] Output   : {output_path}")

    return output_path
