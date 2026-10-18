"""Export topic-specific BibTeX files from classified BibTeX records.

Run from the repository root:
    python -m scripts.export bibliography/classified_v2.bib --output bibliography/topics

The input is never modified. Existing output files require --overwrite.
Requires bibtexparser>=1.4,<2.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter

CATEGORIES = (
    "general_astrophysics", "gamma_ray_astronomy", "cosmic_rays",
    "pulsars_pwn", "supernova_remnants", "grbs", "multimessenger",
    "instrumentation", "methods_software", "magnetic_fields",
    "active_galactic_nuclei",
)
# Keep the original topic filename from the initial repository layout.
FILENAMES = {category: f"{category}.bib" for category in CATEGORIES}
FILENAMES["general_astrophysics"] = "astrophysics.bib"


def parse_bib(path: Path):
    parser = BibTexParser(common_strings=True, interpolate_strings=False)
    with path.open(encoding="utf-8") as stream:
        return bibtexparser.load(stream, parser=parser)


def labels_from_entry(entry):
    raw = entry.get("bib_categories", "")
    return {part.strip().lower() for part in re.split(r"[,;]", raw) if part.strip()}


def render(entries):
    writer = BibTexWriter()
    writer.order_entries_by = None
    writer.indent = "    "
    writer.comma_first = False
    db = bibtexparser.bibdatabase.BibDatabase()
    db.entries = entries
    return bibtexparser.dumps(db, writer=writer)


def export_topics(source: Path, output: Path, overwrite: bool = False):
    if not source.is_file():
        raise FileNotFoundError(source)
    db = parse_bib(source)
    entries = db.entries
    keys = [e["ID"] for e in entries]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate BibTeX keys in source; export aborted")

    groups = {cat: [] for cat in CATEGORIES}
    unclassified = []
    unknown_labels = Counter()
    for entry in entries:
        labels = labels_from_entry(entry)
        for label in labels - set(CATEGORIES):
            unknown_labels[label] += 1
        assigned = labels & set(CATEGORIES)
        if not assigned:
            unclassified.append(entry)
        for cat in assigned:
            groups[cat].append(entry)

    output = output.resolve()
    source = source.resolve()
    targets = {output / FILENAMES[cat]: render(groups[cat]) for cat in CATEGORIES}
    targets[output / "unclassified.bib"] = render(unclassified)
    summary_path = output / "export_summary.json"
    if source in targets or source == summary_path:
        raise ValueError("Output would overwrite the input")
    existing = [p for p in [*targets, summary_path] if p.exists()]
    if existing and not overwrite:
        raise FileExistsError("Outputs already exist: " + ", ".join(str(p) for p in existing[:4]) + ". Use --overwrite to replace generated outputs.")

    summary = {
        "source": str(source), "total_entries": len(entries),
        "classified_entries": len(entries) - len(unclassified),
        "unclassified_entries": len(unclassified),
        "category_counts": {cat: len(groups[cat]) for cat in CATEGORIES},
        "unknown_category_labels": dict(sorted(unknown_labels.items())),
        "note": "Topic files overlap. Do not concatenate them into one LaTeX bibliography.",
    }
    output.mkdir(parents=True, exist_ok=True)
    for path, content in targets.items():
        path.write_text(content, encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Classified BibTeX file")
    parser.add_argument("--output", type=Path, default=Path("bibliography/topics"), help="Topic output directory")
    parser.add_argument("--overwrite", action="store_true", help="Replace previously generated topic files")
    args = parser.parse_args(argv)
    try:
        summary = export_topics(args.source, args.output, args.overwrite)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Exported {summary['total_entries']} source records across {len(CATEGORIES)} topics")
    print(f"Unclassified: {summary['unclassified_entries']}")
    for cat, count in summary["category_counts"].items():
        print(f"  {FILENAMES[cat]}: {count}")


if __name__ == "__main__":
    main()
