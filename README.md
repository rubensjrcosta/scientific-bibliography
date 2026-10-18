# Scientific bibliography

Non-destructive BibTeX auditing using `bibtexparser` 1.x.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m scripts.audit bibliography/master.bib --output reports
```

Copy your curated `.bib` to `bibliography/master.bib` first. The auditor never writes to this file. Reports are diagnostic and do not automatically remove or modify entries.

A valid-looking record is not proof of accurate bibliographic metadata. Duplicate DOI/title groups are candidates for manual review.
