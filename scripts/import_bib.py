"""Safely import new BibTeX records and regenerate topic bibliographies.

Run from repository root:
    python -m scripts.import_bib imports/novo.bib

Requires existing scripts/classify.py, scripts/export.py and bibtexparser 1.x.
The master file is backed up before replacement; ambiguous records are skipped.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import tempfile

import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter

from scripts.classify import classify_detailed
from scripts.export import CATEGORIES, FILENAMES, labels_from_entry, render


def read_bib(path: Path, strict=True):
    parser = BibTexParser(common_strings=True, interpolate_strings=False)
    parser.ignore_nonstandard_types = False
    parser.homogenize_fields = False
    db = bibtexparser.loads(path.read_text(encoding='utf-8-sig'), parser=parser)
    if not db.entries:
        raise ValueError(f'Arquivo sem referências: {path}')
    keys = [e.get('ID', '') for e in db.entries]
    if strict and (not all(keys) or len(keys) != len({k.casefold() for k in keys})):
        raise ValueError(f'Chaves vazias ou repetidas no arquivo: {path}')
    return db


def norm_doi(value):
    value = str(value or '').strip().lower()
    value = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', value)
    return re.sub(r'^doi:\s*', '', value).strip().rstrip('/')


def norm_title(value):
    value = re.sub(r'\\[a-zA-Z]+\s*', '', str(value or ''))
    return re.sub(r'[^\w]+', '', value.casefold(), flags=re.UNICODE)


def title_id(entry):
    value = norm_title(entry.get('title', ''))
    if len(value) < 16 or value in {'notitle', 'unknown', 'untitled'} or value.startswith('notitle'):
        return ''
    return value


def duplicates(existing, candidate):
    reasons = []
    key = candidate['ID'].casefold()
    doi = norm_doi(candidate.get('doi'))
    title = title_id(candidate)
    for old in existing:
        matched = []
        if key == old['ID'].casefold():
            matched.append('key')
        if doi and doi == norm_doi(old.get('doi')):
            matched.append('doi')
        if title and title == title_id(old):
            matched.append('title')
        if matched:
            reasons.append({'key': old['ID'], 'by': matched})
    return reasons


def build_plan(master_entries, incoming_entries):
    accepted = []
    skipped = []
    pending = []
    for entry in incoming_entries:
        matches = duplicates([*master_entries, *accepted], entry)
        if matches:
            # Conflicting identities should be inspected rather than silently discarded.
            target_keys = {match['key'] for match in matches}
            record = {'key': entry['ID'], 'matches': matches}
            if len(target_keys) > 1:
                pending.append({
                    **record,
                    'reason': 'conflicting_matches'
                })
            
            elif any('doi' in match['by'] for match in matches):
                skipped.append(record)
            
            else:
                pending.append({
                    **record,
                    'reason': 'possible_duplicate'
                })
        elif not title_id(entry) or not entry.get('year', '').strip():
            pending.append({'key': entry['ID'], 'reason': 'missing_or_suspicious_title_or_year'})
        else:
            accepted.append(dict(entry))
    return accepted, skipped, pending


def write_db(db, path):
    writer = BibTexWriter()
    writer.order_entries_by = None
    writer.indent = '  '
    path.write_text(bibtexparser.dumps(db, writer=writer), encoding='utf-8')


def run(source: Path, library: Path, topics: Path, dry_run=False):
    source, library, topics = source.resolve(), library.resolve(), topics.resolve()
    if source == library:
        raise ValueError('Arquivo importado e biblioteca principal devem ser diferentes')
    if not source.is_file() or not library.is_file():
        raise FileNotFoundError('Arquivo importado ou biblioteca principal não encontrado')
    master_db, new_db = read_bib(library), read_bib(source, strict=False)
    key_counts = Counter(e.get('ID', '').casefold() for e in new_db.entries)
    good = []
    invalid = []
    for index, entry in enumerate(new_db.entries, start=1):
        key = entry.get('ID', '')
        if not key:
            invalid.append({'key': '', 'reason': 'empty_key', 'source_entry': index})
        elif key_counts[key.casefold()] > 1:
            invalid.append({'key': key, 'reason': 'repeated_source_key', 'source_entry': index})
        else:
            good.append(entry)
    accepted, skipped, pending = build_plan(master_db.entries, good)
    pending = invalid + pending
    result = {'existing': len(master_db.entries), 'incoming': len(new_db.entries),
              'added': len(accepted), 'duplicates': len(skipped),
              'review': len(pending), 'total': len(master_db.entries) + len(accepted),
              'added_keys': [e['ID'] for e in accepted], 'skipped': skipped, 'pending': pending}
    if not dry_run:
        report_dir = library.parent.parent / 'reports' / 'import'
        report_dir.mkdir(parents=True, exist_ok=True)
        report = report_dir / 'import_report.json'
        report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        with (report_dir / 'review.csv').open('w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['key', 'reason', 'source_entry', 'matches'])
            writer.writeheader()
            for item in pending:
                writer.writerow({k: json.dumps(item.get(k, []), ensure_ascii=False) if k == 'matches' else item.get(k, '') for k in writer.fieldnames})
    if dry_run or not accepted:
        return result

    # Generate everything in a temporary directory before touching existing outputs.
    with tempfile.TemporaryDirectory(prefix='bib-import-') as tmp:
        stage = Path(tmp)
        new_entries = [dict(e) for e in master_db.entries] + accepted
        for entry in new_entries:
            labels, _, _, _, _ = classify_detailed(entry)
            if labels:
                entry['bib_categories'] = ', '.join(labels)
            else:
                entry.pop('bib_categories', None)
        master_db.entries = new_entries
        staged_library = stage / 'references.bib'
        write_db(master_db, staged_library)
        check = read_bib(staged_library)
        if len(check.entries) != result['total']:
            raise ValueError('Falha de integridade ao exportar a biblioteca')
        groups = {cat: [] for cat in CATEGORIES}
        unclassified = []
        for entry in check.entries:
            labels = labels_from_entry(entry)
            assigned = labels & set(CATEGORIES)
            if not assigned:
                unclassified.append(entry)
            for label in assigned:
                groups[label].append(entry)
        staged_topics = stage / 'topics'
        staged_topics.mkdir()
        for cat, entries in groups.items():
            (staged_topics / FILENAMES[cat]).write_text(render(entries), encoding='utf-8')
        (staged_topics / 'unclassified.bib').write_text(render(unclassified), encoding='utf-8')
        # Prepare the export report in the temporary directory.
        staged_export_report = stage / 'export_summary.json'
        
        staged_export_report.write_text(
            json.dumps({
                'total_entries': len(check.entries),
                'unclassified_entries': len(unclassified),
                'category_counts': {
                    cat: len(entries)
                    for cat, entries in groups.items()
                },
            }, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8',
        )

        # Keep a timestamped backup outside the generated topics directory.
        backup_dir = library.parent / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = backup_dir / f'references-{stamp}.bib'
        shutil.copy2(library, backup)
        result['backup'] = str(backup)
        # Replace files only after successful generation and validation.
        staged_library.replace(library)
        topics.mkdir(parents=True, exist_ok=True)
        for path in staged_topics.iterdir():
            path.replace(topics / path.name)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Importa, evita duplicatas e atualiza arquivos temáticos')
    parser.add_argument('source', type=Path, help='Novo arquivo .bib')
    parser.add_argument('--library', type=Path, default=Path('bibliography/references.bib'))
    parser.add_argument('--topics', type=Path, default=Path('bibliography/topics'))
    parser.add_argument('--dry-run', action='store_true', help='Mostra o resultado sem modificar arquivos')
    args = parser.parse_args(argv)
    try:
        result = run(args.source, args.library, args.topics, args.dry_run)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Biblioteca: {result['existing']} | Arquivo novo: {result['incoming']}")
    print(f"Adicionadas: {result['added']} | Duplicatas: {result['duplicates']} | Revisar: {result['review']}")
    print(f"Total: {result['total']}")
    if result['review']:
        print('Revisar estas chaves:', ', '.join(item['key'] for item in result['pending']))
    if args.dry_run:
        print('Simulação: nenhum arquivo alterado.')
    elif result['added']:
        print('Biblioteca e tópicos atualizados. Backup:', result['backup'])
    else:
        print('Nenhuma referência nova adicionada; biblioteca preservada.')
    if not args.dry_run:
        print('Relatórios: reports/import/import_report.json e reports/import/review.csv')
    return result


if __name__ == '__main__':
    main()
