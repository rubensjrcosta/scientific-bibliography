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
    "gamma_ray_astronomy": [r"gamma[ -]?rays?", r"γ[ -]?rays?", r"\b(?:tev|gev|vhe)\b", r"cherenkov telescope", r"h\.e\.s\.s\.", r"\bhess j\d", r"\bveritas\b", r"\blhaaso\b", r"\bhawc\b", r"\bfermi[ -]?(?:lat|large area telescope)\b", r"\b(?:[234]fgl)(?:-dr\d+)?\b", r"\bmagic telescopes?\b"],
    "cosmic_rays": [r"cosmic[ -]?rays?", r"\buhecrs?\b", r"ultra[ -]?high[ -]?energy cosmic", r"\bpevatron", r"\bgalprop\b", r"diffusive shock acceleration", r"pierre auger", r"\bauger observatory\b"],
    "pulsars_pwn": [r"pulsars?", r"pulsar wind nebulae?", r"\bpwn\b", r"\bpsr j\d", r"magnetars?", r"spin[ -]?down"],
    "supernova_remnants": [r"supernova remnants?", r"\bsnrs?\b", r"shell[ -]?type remnants?"],
    "grbs": [r"gamma[ -]?ray bursts?", r"\bgrbs?\b", r"afterglow", r"prompt emission", r"fireball model"],
    "multimessenger": [r"multi[ -]?messenger", r"neutrinos?", r"icecube", r"km3net", r"gravitational[ -]?waves?", r"\bligo\b", r"\bvirgo detector\b"],
    "instrumentation": [r"instrument response", r"effective area", r"point[ -]?spread function", r"detector calibration", r"telescope performance", r"observatory design", r"\bctao\b", r"cherenkov telescope array", r"\bswgo\b", r"\b(?:[234]fgl)(?:-dr\d+)?\b", r"source catalog(?:ue)?", r"\b(?:telescope|detector) array\b"],
    "methods_software": [r"\bgammapy\b", r"\bnaima\b", r"\bastropy\b", r"\bscipy\b", r"markov chain monte carlo", r"\bmcmc\b", r"maximum likelihood", r"bayesian inference", r"information theory", r"statistical inference", r"\bpython package\b"],
    "general_astrophysics": [r"stellar evolution", r"interstellar medium", r"galactic structure", r"star formation", r"cosmolog", r"black holes?", r"radiative transfer", r"accretion disk", r"accretion disc"],
    "active_galactic_nuclei": [r"active galactic nuclei", r"active galactic nucleus", r"\bagn\b", r"blazars?", r"seyfert", r"\bfsrq\b", r"\bbl lac\b"],
    "magnetic_fields": [r"magnetic fields?", r"magnetohydrodynamic", r"\bmhd\b", r"magnetic turbulence", r"magnetic reconnection", r"faraday rotation"],
}
COMPILED = {cat: [re.compile(p, re.I) for p in patterns] for cat, patterns in RULES.items()}
FIELDS = ("title", "abstract", "keywords")
WEIGHTS = {"title": 3, "keywords": 2, "abstract": 1}
# A precise, recognizable entity in an abstract can justify a label on its own.
SPECIFIC_ABSTRACT = re.compile(
    r"\b(?:uhecrs?|[234]fgl(?:-dr\d+)?|fermi[ -]?lat|gammapy|naima|astropy|"
    r"icecube|km3net|ctao|swgo|pwn|snr|grbs?|galprop|mcmc|blazar|fsrq)\b",
    re.I,
)
PLACEHOLDER = re.compile(r"^\s*(?:no\s*title|untitled|unknown|n/?a)\s*$", re.I)


def _bad_title(title: str) -> bool:
    t = re.sub(r"[{}]", "", title).strip().lower()
    return (not t or bool(PLACEHOLDER.fullmatch(t))
            or t.startswith("no title")
            or (t.startswith("no ") and t.endswith("title")))


def classify_detailed(entry: dict, threshold: int = 2) -> tuple[list[str], dict, str, dict, dict]:
    """Return categories, evidence, status, scores, and confidence per category."""
    if _bad_title(str(entry.get("title", ""))):
        return [], {}, "review_title", {}, {}
    scores = Counter()
    evidence = {}
    for category, patterns in COMPILED.items():
        hits = []
        for field in FIELDS:
            value = str(entry.get(field, ""))
            for pattern in patterns:
                match = pattern.search(value)
                if match:
                    score = WEIGHTS[field]
                    if field == "abstract" and SPECIFIC_ABSTRACT.search(match.group(0)):
                        score = max(score, 2)
                    scores[category] += score
                    hits.append(f"{field}:{match.group(0)}")
        if hits:
            evidence[category] = sorted(set(hits))
    labels = sorted(cat for cat, score in scores.items() if score >= threshold)
    confidence = {}
    for cat in labels:
        fields = {hit.split(":", 1)[0] for hit in evidence[cat]}
        confidence[cat] = ("high" if scores[cat] >= 5 and len(fields) >= 2
                           else "medium" if scores[cat] >= 3 else "low")
    return labels, {c: evidence[c] for c in labels}, ("classified" if labels else "unclassified"), dict(scores), confidence


def classify_entry(entry: dict, threshold: int = 2) -> tuple[list[str], dict, str]:
    """Backward-compatible three-value classification interface."""
    labels, evidence, status, _, _ = classify_detailed(entry, threshold)
    return labels, evidence, status


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
        labels, evidence, status, scores, confidence = classify_detailed(entry, threshold)
        counts.update(labels)
        rows.append({"key": entry["ID"], "title": entry.get("title", ""),
                     "categories": ";".join(labels), "status": status,
                     "evidence": json.dumps(evidence, ensure_ascii=False, sort_keys=True),
                     "scores": json.dumps(scores, sort_keys=True),
                     "confidence": json.dumps(confidence, sort_keys=True),
                     "decision": "pending" if status != "classified" else "", "notes": ""})
        # Only add a new classification field; never replace user-provided keywords.
        if labels:
            entry["bib_categories"] = ", ".join(labels)
        else:
            entry.pop("bib_categories", None)
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
        if any(entry.get(field) != value for field, value in original[key].items() if field != "bib_categories"):
            raise ValueError(f"Unexpected metadata modification for {key}")
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise RuntimeError("Source changed during classification")
    stats = {"source": str(source), "sha256_source": digest,
             "total_entries": len(rows), "classified": sum(r["status"] == "classified" for r in rows),
             "unclassified": sum(r["status"] == "unclassified" for r in rows),
             "review_title": sum(r["status"] == "review_title" for r in rows),
             "category_counts": dict(sorted(counts.items())),
             "note": "Rule-based suggestions, not verified subject classifications.",
             "low_confidence": sum("low" in r["confidence"] for r in rows)}
    for path in (output, report, summary):
        path.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    with report.open("w", newline="", encoding="utf-8") as f:
        writer_csv = csv.DictWriter(f, fieldnames=["key", "title", "categories", "status", "evidence", "scores", "confidence", "decision", "notes"])
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
