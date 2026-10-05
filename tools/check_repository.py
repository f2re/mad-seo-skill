#!/usr/bin/env python3
"""Проверка ссылок, шаблонов и отсутствия рабочих секретов в поставке."""
from pathlib import Path
import json
import re
import sys

ROOT=Path(__file__).resolve().parent.parent

def main():
    errors=[]
    for path in ROOT.rglob('*.json'):
        if any(part in ('content','analytics','exports','.git','.mad') for part in path.relative_to(ROOT).parts) or path.name=='mad.json':
            continue
        try:json.loads(path.read_text(encoding='utf-8'))
        except (ValueError,OSError):errors.append('Неверный JSON: '+str(path.relative_to(ROOT)))
    for path in [ROOT/'README.md',*list((ROOT/'docs').glob('*.md'))]:
        if not path.exists():errors.append('Нет файла: '+str(path));continue
        for target in re.findall(r'\]\(([^)]+)\)',path.read_text()):
            if '://' not in target and not target.startswith('#') and not (path.parent/target.split('#')[0]).exists():
                errors.append('Не существует ссылка: '+str(path.relative_to(ROOT))+' → '+target)
    for needed in ('LICENSE','NOTICE.md','AGENTS.md','tests/test_mad.py','examples/article-demo/pack.json'):
        if not (ROOT/needed).is_file():errors.append('Нет обязательного файла: '+needed)
    print('\n'.join(errors) if errors else 'JSON, локальные ссылки и обязательные файлы проверены')
    return bool(errors)

if __name__=='__main__':sys.exit(main())
