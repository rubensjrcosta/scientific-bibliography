# BibTeX normalizer v1

Copy `scripts/normalize.py` and `tests/test_normalize.py` into your repository.
Add `bib-normalize = "scripts.normalize:main"` under `[project.scripts]` in `pyproject.toml` (optional; `python -m` works without it).

```bash
python -m pip install -e '.[dev]'
pytest -v
python -m scripts.normalize bibliography/master.bib --output bibliography/normalized.bib --report reports/normalization_report.csv
```

The tool refuses to overwrite existing outputs. Remove/rename generated output and report before rerunning. It preserves keys and does not edit the source. Serialization may reformat the generated BibTeX, so review the diff. Titles, authors, abstracts and URLs are left unchanged. It does not repair bibliographic inaccuracies or remove suspicious records.
