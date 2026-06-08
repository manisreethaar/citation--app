"""
cli.py  —  Command-line interface for auto-citer v2
====================================================

Usage:
  python cli.py --input paper.docx --style apa
  python cli.py --input paper.pdf  --style vancouver --report
  python cli.py --input paper.txt  --style ieee --output cited.txt
"""

import argparse
import sys
from pipeline import process_file
from style_engine import SUPPORTED_STYLES


def main():
    parser = argparse.ArgumentParser(
        description='Auto-Citer v2 — Automatic academic reference citation.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument('--input',  '-i', required=True,
                        help='Input document (.docx, .pdf, or .txt)')
    parser.add_argument('--style',  '-s', default='apa',
                        choices=SUPPORTED_STYLES,
                        help='Citation style (default: apa)')
    parser.add_argument('--output', '-o', default=None,
                        help='Output file (default: <input>_cited.<ext>)')
    parser.add_argument('--report', '-r', action='store_true',
                        help='Print coverage report after processing')

    args = parser.parse_args()

    try:
        process_file(args.input, args.style, args.output, args.report)
    except ValueError as e:
        print(f"[Error] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
