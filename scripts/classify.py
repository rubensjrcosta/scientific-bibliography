"""Non-destructive, explainable multi-label classification of BibTeX entries.

Requires bibtexparser>=1.4,<2. Run from repository root:
python -m scripts.classify bibliography/normalized.bib \
  --output bibliography/classified.bib --report reports/classification_report.csv \
  --summary reports/classification_summary.json
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter

# Expressions are deliberately specific: ambiguous words (e.g. "shock", "magic",
# "cta", "fermi") should not independently determine a category.
RULES = {
    "gamma_ray_astronomy": [r"gamma[ -]?ray", r"γ[ -]?ray", r"tev emission", r"gev emission", r"cherenkov telescope", r"h\.e\.s\.s\.", r"\bhess j\d", r"\bveritas\b", r"\blhaaso\b", r"\bhawc\b", r"\bfermi[ -]?lat\b", r"\bmagic telescopes?\b"],
    "cosmic_rays": [r"cosmic[ -]?rays?", r"pevatron", r"galprop", r"diffusive shock acceleration", r"particle acceleration", r"particle propagation"],
    "pulsars_pwn": [r"pulsar", r"pulsar wind nebula", r"\bpwn\b", r"\bpsr j\d", r"magnetar", r"spin[ -]?down"],
    "supernova_remnants": [r"supernova remnants?", r"\bsnr\b", r"shell[ -]?type remnant"],
    "grbs": [r"gamma[ -]?ray bursts?", r"\bgrbs?\b", r"afterglow", r"prompt emission", r"fireball model"],
    "multimessenger": [r"multimessenger", r"multi[ -]?messenger", r"neutrino", r"icecube", r"km3net", r"gravitational[ -]?wave", r"\bligo\b", r"\bvirgo\b"],
    "instrumentation": [r"instrument response", r"effective area", r"point[ -]?spread function", r"detector calibration", r"telescope performance", r"observatory design", r"\bctao\b", r"cherenkov telescope array", r"\bimaging atmospheric cherenkov\b"],
    "methods_software": [r"\bgammapy\b", r"\bnaima\b", r"\bastropy\b", r"\bscipy\b", r"\bmarkov chain monte carlo\b", r"\bmcmc\b", r"maximum likelihood", r"bayesian inference", r"\bpython package\b"],
    "general_astrophysics": [r"stellar evolution", r"interstellar medium", r"galactic structure", r"star formation", r"cosmolog", r"active galactic nuclei", r"\bagn\b", r"black hole", r"radiative transfer"],
}
COMPILED = {cat: [re.compile(p, re.I) for p in patterns] for cat, patterns in RULES.items()}
# Existing keyword field is not modified: use a separate field for proposed labels.
FIELDS = ("title", "abstract", "keywords")
WEIGHTS = {"title": 3, "keywords": 2, "abstract": 1}
PLACEHOLDER = re.compile(r"^\s*(?:no\s*title|untitled|unknown|n/?a)\s*$", re.I)


def classify_entry(entry: dict, threshold: int = 2) -> tuple[list[str], dict, str]:
    """Return labels, matching evidence, and review status."""
    title = entry.get("title", "")
    if not title or PLACEHOLDER.fullmatch(title) or title.lower().startswith("no title") or title.lower().startswith("no ") and title.lower().endswith("title"):
        return [], {}, "review_title"
    scores = Counter()
    evidence = {}
    for category, patterns in COMPILED.items():
        hits = []
        for field in FIELDS:
            value = str(entry.get(field, ""))
            for pattern in patterns:
                match = pattern.search(value)
                if match:
                    hits.append(f"{field}:{match.group(0)}")
                    scores[category] += WEIGHTS[field]
        if hits:
            evidence[category] = sorted(set(hits))
    labels = sorted(c for c, score in scores.items() if score >= threshold)
    if not labels:
        return [], evidence, "unclassified"
    return labels, {c: evidence[c] for c in labels}, "classified"


def load(path: Path):
    parser = BibTexParser(common_strings=True, interpolate_strings=False)
    parser.ignore_nonstandard_types = False
    parser.homogenize_fields = False
    return bibtexparser.loads(path.read_text(encoding="utf-8-sig"), parser=parser)


def run(source: Path, output: Path, report: Path, summary: Path, threshold: int = 2):
    paths = [p.resolve() for p in (source, output, report, summary)]
    if len(set(paths)) != 4:
        raise ValueError("Input and output paths must all be different")
    if not source.is_file():
        raise FileNotFoundError(source)
    for p in (output, report, summary):
        if p.exists():
            raise FileExistsError(f"Refusing to overwrite: {p}")
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    db = load(source)
    if not db.entries:
        raise ValueError("Empty BibTeX database")
    keys = [e.get("ID", "") for e in db.entries]
    if not all(keys) or len(keys) != len(set(keys)):
        raise ValueError("Missing or duplicate citation keys")
    rows = []
    counts = Counter()
    for entry in db.entries:
        labels, evidence, status = classify_entry(entry, threshold)
        counts.update(labels)
        rows.append({"key": entry["ID"], "title": entry.get("title", ""),
                     "categories": ";".join(labels), "status": status,
                     "evidence": json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                     "decision": "pending" if status != "classified" else "", "notes": ""})
        # Only add a new classification field; never replace user-provided keywords.
        if labels:
            entry["bib_categories"] = ", ".join(labels)
    writer = BibTexWriter()
    writer.order_entries_by = None
    writer.indent = "  "
    writer.add_trailing_comma = True
    rendered = bibtexparser.dumps(db, writer=writer)
    roundtrip = bibtexparser.loads(rendered, parser=BibTexParser(common_strings=True, interpolate_strings=False))
    if [e["ID"] for e in roundtrip.entries] != keys:
        raise ValueError("Round-trip failed to preserve citation keys")
    # Compare every original field against the generated output.
    original = {e["ID"]: e for e in load(source).entries}
    for entry in roundtrip.entries:
        key = entry["ID"]
        if any(entry.get(field) != value for field, value in original[key].items()):
            raise ValueError(f"Unexpected metadata modification for {key}")
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise RuntimeError("Source changed during classification")
    stats = {"source": str(source), "sha256_source": digest,
             "total_entries": len(rows), "classified": sum(r["status"] == "classified" for r in rows),
             "unclassified": sum(r["status"] == "unclassified" for r in rows),
             "review_title": sum(r["status"] == "review_title" for r in rows),
             "category_counts": dict(sorted(counts.items())),
             "note": "Rule-based suggestions, not verified subject classifications."}
    for path in (output, report, summary):
        path.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    with report.open("w", newline="", encoding="utf-8") as f:
        writer_csv = csv.DictWriter(f, fieldnames=["key", "title", "categories", "status", "evidence", "decision", "notes"])
        writer_csv.writeheader()
        writer_csv.writerows(rows)
    summary.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return stats


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    p.add_argument("--summary", type=Path, required=True)
    p.add_argument("--threshold", type=int, default=2)
    args = p.parse_args()
    if args.threshold < 1:
        p.error("--threshold must be >= 1")
    print(json.dumps(run(args.source, args.output, args.report, args.summary, args.threshold), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
