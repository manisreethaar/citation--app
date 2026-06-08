AUTO-CITER  ─  Automatic Reference Citation Tool
==================================================

WHAT IT DOES
  Scans your document body for author name mentions, matches them to the
  reference list at the end, and inserts properly formatted citations.
  Also reformats your bibliography to the chosen style.

SUPPORTED FORMATS
  Input/output: .docx (Word), .pdf, .txt

SUPPORTED CITATION STYLES
  apa        (Smith et al., 2020)          ← social sciences
  vancouver  [1], [2]                      ← biomedical journals
  ieee       [1], [2]                      ← engineering / CS
  nature     [1] / superscript            ← high-impact science

SETUP (one time)
  pip install -r requirements.txt

COMMAND-LINE USAGE
  python auto_citer.py --input paper.docx --style apa
  python auto_citer.py --input paper.pdf  --style vancouver
  python auto_citer.py --input paper.docx --style ieee --report
  python auto_citer.py --input paper.txt  --style nature --output out.txt

  --report    Print a match report showing which refs were found/missed

WEB INTERFACE
  python app.py
  → Open http://localhost:5000 in your browser
  → Drag & drop your document, choose style, click download

HOW YOUR DOCUMENT MUST BE STRUCTURED
  The document must have a "References" (or "Bibliography") section
  heading at the end. References below it can be in any common format:

    Numbered:     1. Smith J et al. (2018) Title. Journal...
    Author-year:  Smith J, Doe A. 2018. Title. Journal...
    Inline year:  Smith J (2018) Title. Journal...

HOW CITATION DETECTION WORKS
  1. The tool parses every reference → extracts first-author surname + year
  2. It scans body text for patterns like:
       "Smith et al. (2018)"  "Smith and Jones (2018)"
       "Johnson (2019)"       "Smith et al."  (year omitted in text)
  3. The citation marker is inserted immediately after the match

TIPS FOR BEST RESULTS
  • Make sure the ref section starts with a line containing only "References"
  • Author names in body text should match the first author in the ref list
  • If a reference is missed, add the author surname + year in the text
  • Run with --report to see which references were not matched

FILES
  auto_citer.py       Main entry-point / pipeline
  reference_parser.py Parse references from document end
  citation_styles.py  Format inline markers + bibliography
  matcher.py          Find citation positions in body text
  file_handlers.py    DOCX / PDF / TXT read-write
  app.py              Flask web interface
  requirements.txt    Python dependencies
