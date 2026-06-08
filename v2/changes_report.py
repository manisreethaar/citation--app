"""
changes_report.py
==================
Produces a human-readable summary of every change the pipeline made:

  1. Citations inserted  — which ref, into which sentence, in which section
  2. Citations replaced  — old marker stripped, new style inserted
  3. Bibliography edits  — how each entry was reformatted
  4. What was NOT touched and why
"""

from dataclasses import dataclass, field
from typing import List, Optional
from reference_model import Reference
from document_model import Sentence, SectionType
from citation_inventory import DetectedCitation


# ─── Change record types ──────────────────────────────────────────────────────

@dataclass
class InsertedCitation:
    reference: Reference
    sentence_text: str
    sentence_index: int
    section: SectionType
    score: float
    was_existing: bool          # True = restored from a stripped marker
    old_marker: Optional[str]   # e.g. "[1]" if converted from another style
    new_marker: str             # e.g. "(Smith et al., 2018)"

    def describe(self) -> str:
        action = "CONVERTED" if self.was_existing else "INSERTED"
        old_part = f'  was: {self.old_marker}' if self.was_existing else ''
        return (
            f"  [{action}] Ref {self.reference.index} — {self.reference.display_label}\n"
            f"  Section : {self.section.value}\n"
            f"  Sentence: \"{self.sentence_text[:120]}{'...' if len(self.sentence_text)>120 else ''}\"\n"
            f"  Marker  : {self.new_marker}{old_part}\n"
            f"  Score   : {self.score:.2f}"
        )


@dataclass
class BibChange:
    reference: Reference
    old_text: str       # raw text from original document
    new_text: str       # reformatted in target style

    def describe(self) -> str:
        if self.old_text.strip() == self.new_text.strip():
            return f"  [UNCHANGED] Ref {self.reference.index} — {self.reference.display_label}"
        return (
            f"  [REFORMATTED] Ref {self.reference.index} — {self.reference.display_label}\n"
            f"  Before: {self.old_text[:120]}\n"
            f"  After : {self.new_text[:120]}"
        )


@dataclass
class ChangesReport:
    style: str
    inserted: List[InsertedCitation] = field(default_factory=list)
    not_cited: List[Reference] = field(default_factory=list)
    bib_changes: List[BibChange] = field(default_factory=list)
    stripped_markers: List[DetectedCitation] = field(default_factory=list)

    # ── Summary counts ────────────────────────────────────────────────────────

    @property
    def n_inserted(self): return sum(1 for c in self.inserted if not c.was_existing)

    @property
    def n_converted(self): return sum(1 for c in self.inserted if c.was_existing)

    @property
    def n_bib_reformatted(self):
        return sum(1 for b in self.bib_changes if b.old_text.strip() != b.new_text.strip())

    # ── Full report text ──────────────────────────────────────────────────────

    def full_report(self) -> str:
        lines = []

        lines += [
            "",
            "=" * 65,
            "  AUTO-CITER — CHANGES REPORT",
            f"  Style: {self.style.upper()}",
            "=" * 65,
            f"  Citations inserted (new)  : {self.n_inserted}",
            f"  Citations converted       : {self.n_converted}  (old style → {self.style.upper()})",
            f"  Bibliography entries reformed: {self.n_bib_reformatted}",
            f"  References not found      : {len(self.not_cited)}",
            "=" * 65,
        ]

        # ── Section 1: Inline citation changes ───────────────────────────────
        if self.inserted:
            lines.append("\n── INLINE CITATION CHANGES ──────────────────────────────────")
            # Group by section
            by_section = {}
            for c in self.inserted:
                by_section.setdefault(c.section.value, []).append(c)

            for section_name, cites in sorted(by_section.items()):
                lines.append(f"\n  [ {section_name.upper()} ]")
                for c in cites:
                    lines.append("")
                    lines.append(c.describe())

        # ── Section 2: Stripped old markers ──────────────────────────────────
        if self.stripped_markers:
            lines.append("\n── OLD MARKERS REMOVED ──────────────────────────────────────")
            lines.append(f"  {len(self.stripped_markers)} existing citation marker(s) were stripped")
            lines.append("  and re-inserted in the target style:")
            for dc in self.stripped_markers:
                lines.append(
                    f"    \"{dc.raw_text}\"  "
                    f"→ resolved to ref(s): {dc.ref_indices}  "
                    f"(detected style: {dc.style_detected})"
                )

        # ── Section 3: Bibliography changes ───────────────────────────────────
        if self.bib_changes:
            lines.append("\n── BIBLIOGRAPHY CHANGES ─────────────────────────────────────")
            for b in self.bib_changes:
                lines.append("")
                lines.append(b.describe())

        # ── Section 4: Not found ──────────────────────────────────────────────
        if self.not_cited:
            lines.append("\n── REFERENCES NOT CITED (action needed) ─────────────────────")
            lines.append("  These references appear in your list but could not be")
            lines.append("  matched to any sentence. Add the author's surname to the")
            lines.append("  relevant sentence and re-run.\n")
            for ref in self.not_cited:
                lines.append(f"  [{ref.index}] {ref.display_label}")
                if ref.title:
                    lines.append(f"       \"{ref.title[:100]}\"")

        lines.append("\n" + "=" * 65 + "\n")
        return "\n".join(lines)

    def print(self):
        print(self.full_report())
