"""
coverage_audit.py
==================
After scoring, check which references have zero confirmed citations.
For uncited references, find the best candidate location and report it
to the user — do NOT silently auto-insert keyword-only matches.

Transparency over automation for ambiguous cases.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from reference_model import Reference
from scoring_engine import Match, THRESHOLD_REVIEW
from document_model import Sentence


@dataclass
class CoverageReport:
    total_refs: int
    auto_cited: List[Reference] = field(default_factory=list)     # score >= AUTO threshold
    needs_review: List[tuple] = field(default_factory=list)       # (ref, best_match)
    uncited: List[Reference] = field(default_factory=list)        # no match found at all

    def summary(self) -> str:
        lines = [
            f"\n{'='*60}",
            f"  CITATION COVERAGE REPORT",
            f"{'='*60}",
            f"  Total references : {self.total_refs}",
            f"  Auto-cited       : {len(self.auto_cited)}  OK",
            f"  Needs review     : {len(self.needs_review)}  REVIEW",
            f"  Not found        : {len(self.uncited)}  MISSING",
            f"{'='*60}",
        ]

        if self.needs_review:
            lines.append("\n  REVIEW NEEDED - low-confidence matches:")
            for ref, match in self.needs_review:
                lines.append(
                    f"    [{ref.index}] {ref.display_label}"
                )
                lines.append(
                    f"        Best candidate (score {match.score:.2f}):"
                )
                lines.append(
                    f"        \"{match.sentence.text[:100]}...\""
                )
                lines.append(
                    f"        Section: {match.sentence.section_type.value}"
                )

        if self.uncited:
            lines.append("\n  NOT FOUND - add author name to text manually:")
            for ref in self.uncited:
                lines.append(f"    [{ref.index}] {ref.display_label}")
                if ref.title:
                    lines.append(f"        Title: {ref.title[:80]}")

        lines.append('=' * 60 + '\n')
        return '\n'.join(lines)


def audit_coverage(refs: List[Reference],
                   all_matches: List[Match],
                   confirmed_indices: Dict[int, bool]) -> CoverageReport:
    """
    Build a coverage report.

    confirmed_indices: set of ref.index values that were auto-confirmed
    all_matches: all matches above THRESHOLD_REVIEW (from score_document)
    """
    report = CoverageReport(total_refs=len(refs))

    # Group matches by reference
    by_ref: Dict[int, List[Match]] = {}
    for m in all_matches:
        by_ref.setdefault(m.reference.index, []).append(m)

    for ref in refs:
        if confirmed_indices.get(ref.index):
            report.auto_cited.append(ref)
        elif ref.index in by_ref:
            best = sorted(by_ref[ref.index], key=lambda x: x.score, reverse=True)[0]
            report.needs_review.append((ref, best))
        else:
            report.uncited.append(ref)

    return report
