"""Conservative, non-destructive BibTeX normalization (bibtexparser 1.x).

Run: python -m scripts.normalize bibliography/master.bib \
    --output bibliography/normalized.bib --report reports/normalization_report.csv

The source is never written to. Existing citation keys are preserved.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path
import re

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter

DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi\s*:\s*)", re.I)
DOI_VALID = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
# Whitespace is normalized only in these simple metadata fields; titles,
# author names, abstracts, LaTeX commands and URLs are preserved verbatim.
SIMPLE_FIELDS = {"year", "volume", "number", "pages", "eid", "month", "doi", "isbn", "issn"}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def clean_value(field: str, value: str) -> str:
    if field not in SIMPLE_FIELDS:
        return value
    cleaned = re.sub(r"\s+", " ", value).strip()
    if field == "doi":
        cleaned = DOI_PREFIX.sub("", cleaned).strip()
        # Remove a DOI prefix only once; do not rewrite the identifier itself.
    return cleaned


def normalize(source: Path, output: Path, report: Path) -> dict:
    source = source.resolve()
    output = output.resolve()
    report = report.resolve()
    if source == output:
        raise ValueError("Output must differ from the original source (master.bib).")
    if report in (source, output):
        raise ValueError("Report path must differ from source and output.")
    if not source.is_file():
        raise FileNotFoundError(source)
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite existing output: {output}")
    if report.exists():
        raise FileExistsError(f"Refusing to overwrite existing report: {report}")

    raw = source.read_bytes()
    original_hash = sha256(raw)
    parser = BibTexParser(common_strings=True, interpolate_strings=False)
    parser.ignore_nonstandard_types = False
    parser.homogenize_fields = False
    db = bibtexparser.loads(raw.decode("utf-8-sig"), parser=parser)
    if not db.entries:
        raise ValueError("No BibTeX entries found; refusing to write an empty library.")
    keys = [str(entry.get("ID", "")) for entry in db.entries]
    if any(not key for key in keys) or len(keys) != len(set(keys)):
        raise ValueError("Missing or repeated BibTeX keys: resolve before normalization.")

    changes = []
    for entry in db.entries:
        for field, value in list(entry.items()):
            if field in {"ID", "ENTRYTYPE"} or not isinstance(value, str):
                continue
            new = clean_value(field, value)
            if new != value:
                changes.append({"key": entry["ID"], "field": field,
                                "old_value": value, "new_value": new,
                                "status": "changed"})
                entry[field] = new
            if field == "doi" and new and not DOI_VALID.fullmatch(new):
                changes.append({"key": entry["ID"], "field": field,
                                "old_value": value, "new_value": new,
                                "status": "review_invalid_doi"})

    writer = BibTexWriter()
    writer.indent = "  "
    writer.order_entries_by = None
    writer.add_trailing_comma = True
    rendered = bibtexparser.dumps(db, writer=writer)
    # Parse again and check key and entry count before emitting files.
    check = bibtexparser.loads(rendered, parser=BibTexParser(common_strings=True, interpolate_strings=False))
    if len(check.entries) != len(db.entries) or [e["ID"] for e in check.entries] != keys:
        raise ValueError("Round-trip changed entry count or citation keys; output rejected.")
    if sha256(source.read_bytes()) != original_hash:
        raise RuntimeError("Source changed during processing; output rejected.")

    output.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")
    with report.open("w", newline="", encoding="utf-8") as stream:
        csv_writer = csv.DictWriter(stream, fieldnames=["key", "field", "old_value", "new_value", "status"])
        csv_writer.writeheader()
        csv_writer.writerows(changes)
    return {"entries": len(db.entries), "changes": sum(x["status"] == "changed" for x in changes),
            "doi_to_review": sum(x["status"] == "review_invalid_doi" for x in changes),
            "source_sha256": original_hash, "output": str(output), "report": str(report)}


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("source", type=Path)
    cli.add_argument("--output", type=Path, default=Path("bibliography/normalized.bib"))
    cli.add_argument("--report", type=Path, default=Path("reports/normalization_report.csv"))
    args = cli.parse_args()
    result = normalize(args.source, args.output, args.report)
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
