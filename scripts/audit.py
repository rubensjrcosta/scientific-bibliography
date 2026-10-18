"""Audit a BibTeX file without changing it.

Usage:
    python -m scripts.audit bibliography/master.bib --output reports

Uses the stable bibtexparser 1.x API. Reports are diagnostic, not automatic edits.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

import bibtexparser
from bibtexparser.bparser import BibTexParser

# Fields here are a local curation policy, not universal BibTeX requirements.
REQUIRED = {
    "article": ("author", "title", "year", "journal", "volume"),
    "book": ("title", "year", "publisher"),
    "inbook": ("title", "year", "publisher"),
    "incollection": ("author", "title", "year", "booktitle", "publisher"),
    "inproceedings": ("author", "title", "year", "booktitle"),
    "phdthesis": ("author", "title", "year", "school"),
    "mastersthesis": ("author", "title", "year", "school"),
    "techreport": ("author", "title", "year", "institution"),
    "misc": ("title",),
    "online": ("title",),
    "unpublished": ("author", "title", "note"),
}


def normalized_text(value: str) -> str:
    value = re.sub(r"\\[a-zA-Z]+\s*", "", value)
    value = re.sub(r"[^a-z0-9]+", "", value.casefold())
    return value


def normalized_doi(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value)
    return re.sub(r"^doi:\s*", "", value).strip()


PLACEHOLDERS = {"notitle", "untitled", "unknown", "na", "none", "tbd", "missing", "notavailable"}


def is_placeholder(value: str) -> bool:
    return normalized_text(value) in PLACEHOLDERS


def has_value(entry: dict, field: str) -> bool:
    value = str(entry.get(field, "")).strip()
    return bool(value and value not in ("{}", '""') and not is_placeholder(value))


def audit(source: Path) -> dict:
    original = source.read_bytes()
    source_hash = hashlib.sha256(original).hexdigest()
    text = original.decode("utf-8-sig")
    parser = BibTexParser(common_strings=True, interpolate_strings=False)
    parser.ignore_nonstandard_types = False
    parser.homogenize_fields = False
    parser.customization = None
    database = bibtexparser.loads(text, parser=parser)
    entries = database.entries
    issues = []
    groups = {name: defaultdict(list) for name in ("key", "key_casefold", "doi", "title")}
    counts = Counter()

    for index, entry in enumerate(entries, 1):
        key = str(entry.get("ID", "")).strip()
        kind = str(entry.get("ENTRYTYPE", "")).lower()
        counts[kind] += 1
        groups["key"][key].append(key)
        groups["key_casefold"][key.casefold()].append(key)
        if has_value(entry, "doi"):
            groups["doi"][normalized_doi(str(entry["doi"]))].append(key)
        if has_value(entry, "title"):
            title_norm = normalized_text(str(entry["title"]))
            if len(title_norm) >= 12:
                groups["title"][title_norm].append(key)

        def add(code: str, detail: str, severity: str = "warning") -> None:
            issues.append({"entry_number": index, "key": key, "type": kind,
                           "severity": severity, "code": code, "detail": detail})

        for field in ("title", "author", "journal", "publisher"):
            if field in entry and is_placeholder(str(entry[field])):
                add("placeholder_value", f"{field}: {entry[field]}", "review")
        if kind not in REQUIRED:
            add("unknown_type", f"No completeness policy for @{kind}")
        else:
            for field in REQUIRED[kind]:
                if not has_value(entry, field):
                    add("missing_field", field)
            if kind == "book" and not (has_value(entry, "author") or has_value(entry, "editor")):
                add("missing_field", "author or editor")
            if kind in ("misc", "online") and not any(has_value(entry, f) for f in ("doi", "url", "howpublished", "note", "eprint")):
                add("missing_identifier", "doi/url/howpublished/note/eprint")
            if kind == "article" and not any(has_value(entry, f) for f in ("pages", "eid", "number")):
                add("missing_locator", "pages/eid/number (review manually)")

        if has_value(entry, "year") and re.fullmatch(r"\d{4}", str(entry["year"]).strip()):
            year = int(str(entry["year"]).strip())
            if year < 1600 or year > 2030:
                add("suspicious_year", str(year), "review")
        if has_value(entry, "year") and not re.fullmatch(r"\d{4}", str(entry["year"]).strip()):
            add("invalid_year", str(entry["year"]))
        if has_value(entry, "doi") and not re.fullmatch(r"10\.\d{4,9}/\S+", normalized_doi(str(entry["doi"]))):
            add("suspicious_doi", str(entry["doi"]))

    duplicates = []
    for category, index in groups.items():
        for value, keys in index.items():
            if value and len(keys) > 1:
                duplicates.append({"category": category, "value": value,
                                   "count": len(keys), "keys": keys})
                for key in keys:
                    issues.append({"entry_number": "", "key": key, "type": "",
                                   "severity": "review", "code": f"duplicate_{category}",
                                   "detail": f"{value} ({len(keys)} records)"})

    # Review queue: one row per issue, with editable human decision columns.
    return {"source": str(source), "sha256_before": source_hash,
            "total_entries": len(entries), "types": dict(counts),
            "issues": issues, "duplicate_groups": duplicates}


def write_reports(result: dict, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "audit_summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with (output / "audit_issues.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["entry_number", "key", "type", "severity", "code", "detail"])
        writer.writeheader()
        writer.writerows(result["issues"])
    with (output / "manual_review.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["key", "code", "detail", "decision", "notes"])
        writer.writeheader()
        seen = set()
        for issue in result["issues"]:
            signature = (issue["key"], issue["code"], issue["detail"])
            if signature not in seen:
                writer.writerow({"key": issue["key"], "code": issue["code"],
                                 "detail": issue["detail"], "decision": "pending", "notes": ""})
                seen.add(signature)
    with (output / "audit_duplicates.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["category", "value", "count", "keys"])
        for row in result["duplicate_groups"]:
            writer.writerow([row["category"], row["value"], row["count"], "; ".join(row["keys"])])


def main(argv: list[str] | None = None) -> int:
    command = argparse.ArgumentParser(description=__doc__)
    command.add_argument("bibfile", type=Path, help="Input .bib file (read only)")
    command.add_argument("--output", type=Path, default=Path("reports"), help="Report directory")
    args = command.parse_args(argv)
    if not args.bibfile.is_file():
        command.error(f"Input file not found: {args.bibfile}")
    try:
        result = audit(args.bibfile)
        if args.output.resolve() == args.bibfile.resolve():
            raise ValueError("Output directory must differ from input file")
        write_reports(result, args.output)
        if hashlib.sha256(args.bibfile.read_bytes()).hexdigest() != result["sha256_before"]:
            raise RuntimeError("Input file changed during audit")
    except (OSError, UnicodeError, ValueError, RuntimeError) as error:
        print(f"Audit failed: {error}", file=sys.stderr)
        return 2
    print(f"Entries: {result['total_entries']}; issues: {len(result['issues'])}; "
          f"duplicate groups: {len(result['duplicate_groups'])}")
    print(f"Reports saved in {args.output}")
    print("Source file unchanged (SHA-256 verified).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
