# Exportação temática de referências BibTeX

Requer `bibtexparser>=1.4,<2` (a mesma dependência do classificador).

Copie `scripts/export.py` e `tests/test_export.py` para as pastas equivalentes do seu repositório.

```bash
python -m scripts.export bibliography/classified_v2.bib --output bibliography/topics
```

Para regenerar arquivos já existentes:

```bash
python -m scripts.export bibliography/classified_v2.bib --output bibliography/topics --overwrite
```

O comando cria 11 arquivos por tema, `unclassified.bib` e `export_summary.json`.
`astrophysics.bib` corresponde à categoria `general_astrophysics`.
Uma referência pode aparecer em mais de um arquivo temático; não concatene os arquivos.
O campo `bib_categories` precisa existir no arquivo de entrada. A classificação é uma sugestão automática.

Testes:

```bash
pytest -q tests/test_export.py
```
