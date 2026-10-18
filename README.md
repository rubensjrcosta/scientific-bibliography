# Importação de referências

Copie somente `scripts/import_bib.py` para o repositório existente. Os arquivos `scripts/classify.py` e `scripts/export.py` da versão 2 devem continuar instalados.

Prévia, sem alterações:

```bash
python -m scripts.import_bib imports/novo.bib --dry-run
```

Importar referências novas e atualizar os arquivos temáticos:

```bash
python -m scripts.import_bib imports/novo.bib
```

O script compara chaves, DOI e títulos normalizados, pula correspondências e reserva conflitos ou títulos/anos suspeitos para revisão. A classificação automática é uma sugestão e pode conter erros. Cria backup da biblioteca anterior em `bibliography/backups/`. Para evitar enviar backups ao GitHub, inclua `bibliography/backups/` no `.gitignore`.

**Importante:** execute no diretório raiz do repositório e use `bibtexparser>=1.4,<2`. Não misture os arquivos temáticos ao compilar o mesmo documento LaTeX, pois uma referência pode aparecer em mais de um tema.
