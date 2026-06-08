"""
plagiarism_report.py
=====================
Generates a human-readable plagiarism report from engine + web checker results.

Report sections:
  1. Summary — overall similarity %, risk label, source breakdown
  2. Local matches — matched chunks from uploaded source files
  3. Web matches — matched sentences found on the web
  4. Clean passages — chunks with no match (shows what passed)

Usage:
  from plagiarism_report import build_report
  report_text = build_report(engine_result, web_matches, doc_name, source_names)
"""

from typing import List, Optional
from plagiarism_engine import PlagiarismResult, ChunkMatch
from web_checker import WebMatch


def build_report(
    result: PlagiarismResult,
    web_matches: List[WebMatch],
    doc_name: str = "Uploaded document",
    source_names: Optional[List[str]] = None,
) -> str:
    lines = []

    # ── Header ────────────────────────────────────────────────────────────────
    lines += [
        "",
        "=" * 65,
        "  PLAGIARISM CHECK REPORT",
        f"  Document : {doc_name}",
        "=" * 65,
    ]

    # ── Summary ───────────────────────────────────────────────────────────────
    total_matches = len(result.matches) + len(web_matches)

    lines += [
        f"  Overall similarity  : {result.similarity_pct:.1f}%",
        f"  Risk level          : {result.risk_label}",
        f"  Document word count : {result.doc_word_count:,}",
        f"  Flagged word count  : {result.flagged_word_count:,}",
        f"  Local matches found : {len(result.matches)}",
        f"  Web matches found   : {len(web_matches)}",
    ]

    if result.sources_hit():
        lines.append(f"  Sources matched     : {', '.join(result.sources_hit())}")

    lines.append("=" * 65)

    # ── Risk level explanation ─────────────────────────────────────────────────
    risk = result.risk_label
    if risk == "HIGH RISK":
        lines.append(
            "\n  ⚠ HIGH RISK — Substantial portions of this document match\n"
            "  known sources. Review flagged passages before submission."
        )
    elif risk == "MEDIUM RISK":
        lines.append(
            "\n  ⚠ MEDIUM RISK — Some passages match known sources.\n"
            "  Check flagged sections and add proper citations if missing."
        )
    elif risk == "LOW RISK":
        lines.append(
            "\n  ℹ LOW RISK — Minor overlaps detected. Likely acceptable,\n"
            "  but review flagged phrases to confirm they are properly cited."
        )
    else:
        lines.append(
            "\n  ✓ LIKELY ORIGINAL — No significant matches found in the\n"
            "  provided sources or web search."
        )

    # ── Local matches ─────────────────────────────────────────────────────────
    if result.matches:
        lines.append("\n── LOCAL SOURCE MATCHES " + "─" * 41)
        lines.append("  (compared against uploaded reference files)\n")

        # Group by source
        by_source: dict = {}
        for m in result.matches:
            by_source.setdefault(m.source_name, []).append(m)

        for src_name, src_matches in by_source.items():
            high   = [m for m in src_matches if m.risk_level == "HIGH"]
            medium = [m for m in src_matches if m.risk_level == "MEDIUM"]
            low    = [m for m in src_matches if m.risk_level == "LOW"]

            lines.append(
                f"\n  Source: \"{src_name}\"\n"
                f"  {len(high)} HIGH · {len(medium)} MEDIUM · {len(low)} LOW risk matches"
            )
            lines.append("")

            for m in sorted(src_matches, key=lambda x: -x.jaccard):
                lines.append(m.summary())
                lines.append("")
    else:
        lines.append("\n── LOCAL SOURCE MATCHES " + "─" * 41)
        if source_names:
            lines.append(f"  No matches found against: {', '.join(source_names)}")
        else:
            lines.append("  No source files provided for local comparison.")

    # ── Web matches ───────────────────────────────────────────────────────────
    if web_matches:
        lines.append("\n── WEB SEARCH MATCHES " + "─" * 43)
        lines.append("  (phrases found verbatim or near-verbatim on the web)\n")
        for wm in sorted(web_matches, key=lambda x: -x.jaccard):
            lines.append(wm.summary())
            lines.append("")
    else:
        lines.append("\n── WEB SEARCH MATCHES " + "─" * 43)
        lines.append("  No web matches found (or web check was not enabled).")

    # ── What to do ────────────────────────────────────────────────────────────
    if total_matches > 0:
        lines += [
            "\n── RECOMMENDED ACTIONS " + "─" * 42,
            "  HIGH matches  → Rewrite or add explicit citation.",
            "  MEDIUM matches → Verify citation exists; paraphrase if needed.",
            "  LOW matches   → Check for accidental phrase overlap; usually fine.",
        ]

    lines.append("\n" + "=" * 65 + "\n")
    return "\n".join(lines)


def print_report(
    result: PlagiarismResult,
    web_matches: List[WebMatch],
    doc_name: str = "Uploaded document",
    source_names: Optional[List[str]] = None,
):
    print(build_report(result, web_matches, doc_name, source_names))
