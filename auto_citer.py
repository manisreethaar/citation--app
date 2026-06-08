"""
auto_citer.py  ─  Main entry-point (CLI + importable API)
===========================================================

Usage (command line):
  python auto_citer.py --input paper.docx --style apa
  python auto_citer.py --input paper.pdf  --style vancouver --output cited_paper.pdf
  python auto_citer.py --input paper.docx --style ieee --report

Supported styles: apa | vancouver | ieee | nature

Options:
  --input    Path to the input document (.docx or .pdf)
  --style    Citation style (default: apa)
  --output   Output file path (default: <input>_cited.<ext>)
  --report   Print a match report showing which references were found in text
"""

import argparse
import os
import re
import sys
from pathlib import Path

from reference_parser import split_references_from_body, parse_references
from citation_styles import inline_citation, format_bibliography
from matcher import insert_citations
from file_handlers import (
    read_docx, write_docx, read_pdf, write_pdf_txt,
    read_text, write_text, find_refs_start_paragraph
)


_REF_SECTION_RE = re.compile(
    r'^\s*(?:references?|bibliography|works\s+cited|literature\s+cited'
    r'|citations?|sources?)\s*$',
    re.IGNORECASE
)

SUPPORTED_STYLES = ['apa', 'vancouver', 'ieee', 'nature']


# ─────────────────────────────────────────────────────────────────────────────
#  Core pipeline
# ─────────────────────────────────────────────────────────────────────────────

def process_document(input_path: str, style: str = 'apa',
                     output_path: str = None, print_report: bool = False) -> str:
    """
    Main pipeline.
    Returns the output file path.
    """
    style = style.lower()
    if style not in SUPPORTED_STYLES:
        raise ValueError(f"Style '{style}' not supported. Choose from: {SUPPORTED_STYLES}")

    ext = Path(input_path).suffix.lower()
    if output_path is None:
        stem = Path(input_path).stem
        output_path = str(Path(input_path).parent / f"{stem}_cited{ext}")

    print(f"[auto-citer] Reading: {input_path}")
    print(f"[auto-citer] Style: {style.upper()}")

    # ── 1. Read document ─────────────────────────────────────────────────────
    if ext == '.docx':
        full_text, doc_obj = read_docx(input_path)
    elif ext == '.pdf':
        full_text = read_pdf(input_path)
        doc_obj = None
    else:
        full_text = read_text(input_path)
        doc_obj = None

    # ── 2. Split body + references ───────────────────────────────────────────
    body, ref_section = split_references_from_body(full_text)

    if not ref_section.strip():
        print("[auto-citer] WARNING: No reference section found.")
        print("             Ensure your document ends with a 'References' heading.")
        sys.exit(1)

    # ── 3. Parse references ──────────────────────────────────────────────────
    refs = parse_references(ref_section)
    print(f"[auto-citer] Found {len(refs)} references.")

    if not refs:
        print("[auto-citer] ERROR: Could not parse any references.")
        sys.exit(1)

    # ── 4. Insert citations into body ────────────────────────────────────────
    cited_body = insert_citations(body, refs, style)

    # ── 5. Format bibliography ───────────────────────────────────────────────
    new_bibliography = format_bibliography(refs, style)

    # ── 6. Write output ──────────────────────────────────────────────────────
    if ext == '.docx' and doc_obj is not None:
        # Find where references start in the paragraph list
        ref_para_idx = find_refs_start_paragraph(doc_obj, _REF_SECTION_RE)
        write_docx(doc_obj, cited_body, new_bibliography, ref_para_idx, output_path)
    elif ext == '.pdf':
        full_cited = cited_body + '\n\n' + new_bibliography
        write_pdf_txt(full_cited, output_path)
    else:
        full_cited = cited_body + '\n\n' + new_bibliography
        write_text(full_cited, output_path)

    print(f"[auto-citer] Output written: {output_path}")

    # ── 7. Optional match report ──────────────────────────────────────────────
    if print_report:
        _print_report(body, cited_body, refs, style)

    return output_path


# ─────────────────────────────────────────────────────────────────────────────
#  Report
# ─────────────────────────────────────────────────────────────────────────────

def _print_report(original_body: str, cited_body: str,
                  refs, style: str) -> None:
    print('\n' + '=' * 60)
    print('CITATION MATCH REPORT')
    print('=' * 60)
    for ref in refs:
        cite = inline_citation(ref, style)
        if cite in cited_body or f'__CITE_{ref.index}__' in cited_body:
            status = '✓ CITED'
        else:
            # Check if surname appears anywhere
            surname = ref.first_author_surname or ''
            if surname and surname.lower() in original_body.lower():
                status = '? SURNAME FOUND (year mismatch?)'
            else:
                status = '✗ NOT FOUND IN TEXT'
        label = (ref.authors[0] if ref.authors else 'Unknown') + f' ({ref.year or "?"})'
        print(f'  [{ref.index:3d}] {status:40s} {label}')
    print('=' * 60 + '\n')


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Auto-cite references in academic documents.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--input', '-i', required=True,
                        help='Input document (.docx, .pdf, or .txt)')
    parser.add_argument('--style', '-s', default='apa',
                        choices=SUPPORTED_STYLES,
                        help='Citation style (default: apa)')
    parser.add_argument('--output', '-o', default=None,
                        help='Output file path (default: <input>_cited.<ext>)')
    parser.add_argument('--report', '-r', action='store_true',
                        help='Print a citation match report after processing')

    args = parser.parse_args()
    process_document(args.input, args.style, args.output, args.report)


if __name__ == '__main__':
    main()
