# BibTeX audit with comparison

Replace `scripts/audit.py` in your existing repository with the file in this package.

```bash
python -m scripts.audit imports/novo.bib --compare bibliography/references.bib --output reports/comparison
```

The original audit reports are generated as before, plus:

- `comparison.csv`: each imported entry, candidate status, matching criteria, existing keys.
- `comparison_summary.json`: totals by status.

Matching uses normalized DOI, case-insensitive BibTeX key, or normalized title (>=12 characters, excluding placeholder titles). It does not perform fuzzy matching, and `candidate_new` does not prove that a publication is new. No BibTeX input is changed.

To audit only one file:

```bash
python -m scripts.audit imports/novo.bib --output reports/new
```
