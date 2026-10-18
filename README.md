# Classificação temática v2

Atualização não destrutiva do classificador BibTeX. Mantém as chaves e os metadados originais, adicionando/atualizando somente `bib_categories` no arquivo de saída.

## Instalação

Copie `scripts/classify.py` e `tests/test_classify.py` para o repositório. Use `bibtexparser>=1.4,<2` e `pytest`.

## Execução

```bash
python -m scripts.classify bibliography/normalized.bib \
  --output bibliography/classified_v2.bib \
  --report reports/classification_report_v2.csv \
  --summary reports/classification_summary_v2.json
pytest -v tests/test_classify.py
```

Não use os mesmos caminhos da v1, pois o script recusa sobrescrever arquivos existentes. O CSV v2 acrescenta `scores` e `confidence` (low/medium/high por categoria). Classificações são sugestões, não revisão humana. `review_title` e `unclassified` permanecem sinalizadas. O script não altera o arquivo de entrada.

## Limitações

A correspondência é baseada em expressões regulares; termos ambíguos e assuntos pouco representados podem gerar falsos positivos/negativos. Revise sobretudo classificações com baixa confiança e as categorias `instrumentation` e `general_astrophysics`.
