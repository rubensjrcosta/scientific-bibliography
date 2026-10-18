# Classificação temática BibTeX v1

Instale `bibtexparser>=1.4,<2` e `pytest`. Copie `scripts/classify.py` e `tests/test_classify.py` para o repositório.

```bash
python -m scripts.classify bibliography/normalized.bib \
  --output bibliography/classified.bib \
  --report reports/classification_report.csv \
  --summary reports/classification_summary.json
pytest -q tests/test_classify.py
```

O arquivo de entrada nunca é alterado. O classificador adiciona `bib_categories` somente quando encontra evidências suficientes, sem substituir `keywords` ou chaves de citação. Registros sem evidências ficam `unclassified`; títulos suspeitos ficam `review_title`. Os relatórios incluem evidências textuais para revisão. Categorias são sugestões heurísticas, não uma validação científica.

Para repetir a execução, use novos nomes de saída ou remova somente os três arquivos gerados anteriormente.
