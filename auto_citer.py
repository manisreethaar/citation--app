"""
auto_citer.py  ─  Main entry-point (CLI + importable API)
===========================================================

Usage (command line):
  python auto_citer.py --input paper.docx --style apa
  python auto_citer.py --input paper.pdf  --style vancouver --output cited_paper.pdf
  python auto_citer.py --input paper.docx --style ieee --report

Supported styles: apa | vancouver | ieee | nature | mla | chicago

Options:
  --input    Path to the input document (.docx, .pdf, or .txt)
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
from matcher import insert_citations, smart_insert_citations
from citation_detector import detect_citation_mode
from file_handlers import (
    read_docx, write_docx, read_pdf, write_pdf_txt,
    read_text, write_text, find_refs_start_paragraph
)


_REF_SECTION_RE = re.compile(
    r'^\s*(?:references?|bibliography|works\s+cited|literature\s+cited'
    r'|citations?|sources?)\s*$',
    re.IGNORECASE
)

SUPPORTED_STYLES = ['apa', 'vancouver', 'ieee', 'nature', 'mla', 'chicago', 'harvard', 'ama']

# Maximum file size (16 MB)
MAX_FILE_SIZE = 16 * 1024 * 1024


# ─────────────────────────────────────────────────────────────────────────────
#  Core pipeline
# ─────────────────────────────────────────────────────────────────────────────

def process_document(input_path: str, style: str = 'apa',
                     output_path: str = None, print_report: bool = False) -> str:
    """
    Main processing pipeline.

    Args:
        input_path:   Path to .docx, .pdf, or .txt file.
        style:        Citation style (apa, vancouver, ieee, nature, mla, chicago).
        output_path:  Where to save the output (default: <input>_cited.<ext>).
        print_report: If True, print a citation match report to stdout.

    Returns:
        The output file path.

    Raises:
        ValueError: For invalid style or unsupported file type.
        RuntimeError: If no reference section or no references found.
        FileNotFoundError: If input file does not exist.
        OSError: If file exceeds size limit.
    """
    style = style.lower()
    if style not in SUPPORTED_STYLES:
        raise ValueError(
            f"Style '{style}' not supported. Choose from: {', '.join(SUPPORTED_STYLES)}"
        )

    input_path = str(input_path)
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    file_size = os.path.getsize(input_path)
    if file_size > MAX_FILE_SIZE:
        raise OSError(
            f"File too large ({file_size / 1024 / 1024:.1f} MB). "
            f"Maximum allowed: {MAX_FILE_SIZE // 1024 // 1024} MB."
        )

    ext = Path(input_path).suffix.lower()
    supported_exts = {'.docx', '.pdf', '.txt'}
    if ext not in supported_exts:
        raise ValueError(
            f"Unsupported file type '{ext}'. Supported: {', '.join(supported_exts)}"
        )

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

    if not full_text or not full_text.strip():
        raise RuntimeError("The document appears to be empty or could not be read.")

    # ── 2. Split body + references ───────────────────────────────────────────
    body, ref_section = split_references_from_body(full_text)

    if not ref_section.strip():
        raise RuntimeError(
            "No reference section found. "
            "Ensure your document ends with a 'References' (or 'Bibliography') heading."
        )

    # ── 3. Detect existing citation mode ─────────────────────────────
    detection = detect_citation_mode(body)
    print(f"[auto-citer] Citation mode: {detection['mode']} ({detection['count']} markers)")

    # ── 4. Parse references ─────────────────────────────────────────
    refs = parse_references(ref_section)
    print(f"[auto-citer] Found {len(refs)} references.")

    if not refs:
        raise RuntimeError(
            "Could not parse any references from the reference section. "
            "Check that references are properly formatted."
        )

    # ── 5. Insert / reformat citations ──────────────────────────────
    cited_body, mode_desc = smart_insert_citations(body, refs, style)
    print(f"[auto-citer] {mode_desc}")

    # ── 6. Format bibliography ──────────────────────────────────────
    new_bibliography = format_bibliography(refs, style)

    # ── 7. Write output ─────────────────────────────────────────────
    if ext == '.docx' and doc_obj is not None:
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
            surname = ref.first_author_surname or ''
            if surname and surname.lower() in original_body.lower():
                status = '? SURNAME FOUND (year mismatch?)'
            else:
                status = '✗ NOT FOUND IN TEXT'
        label = (ref.authors[0] if ref.authors else 'Unknown') + f' ({ref.year or "?"})'
        print(f'  [{ref.index:3d}] {status:40s} {label}')
    print('=' * 60 + '\n')


def build_report(body: str, cited_body: str, refs, style: str) -> str:
    """Return match report as a string (for web UI display)."""
    lines = ['Citation Match Report', '=' * 50]
    cited_count = 0
    for ref in refs:
        cite = inline_citation(ref, style)
        if cite in cited_body:
            status = '✓ cited'
            cited_count += 1
        else:
            surname = ref.first_author_surname or ''
            if surname and surname.lower() in body.lower():
                status = '? surname found'
            else:
                status = '✗ not found'
        label = (ref.authors[0] if ref.authors else 'Unknown') + f' ({ref.year or "?"})'
        lines.append(f'[{ref.index:3d}] {status:18s} {label}')
    lines.append('=' * 50)
    lines.append(f'Total: {cited_count}/{len(refs)} references cited.')
    return '\n'.join(lines)


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
    try:
        process_document(args.input, args.style, args.output, args.report)
    except (ValueError, RuntimeError, FileNotFoundError, OSError) as e:
        print(f"[auto-citer] ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
