"""Обязательное исследование перед планом и статьёй. Сеть использует агент, не CLI."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from urllib.parse import urlsplit

from . import core
from .research import measured_trend, normalized_url

MAX_AGE_DAYS = 7
PLATFORMS = {'forum', 'vk', 'instagram', 'tiktok'}
STATUSES = {'read', 'metadata_only', 'blocked', 'not_checked'}


def today():
    return datetime.now(timezone.utc).date()


def folder(root, run):
    return core.safe(root, 'content/research/' + core.ident(run))


def registry(root):
    rows = core.knowledge(root, 'community-sources.json')
    if not isinstance(rows, list) or len({x['id'] for x in rows}) != len(rows):
        raise core.MadError('Некорректный реестр сообществ')
    for row in rows:
        core.ident(row['id']); core.url(row['profile_url'])
        if row['relationship'] not in ('owned', 'external') or not row['publisher_group']:
            raise core.MadError('У источника нужны relationship и publisher_group')
    return {x['id']: x for x in rows}


def belongs(address, source):
    """Для соцсетей проверять профиль/известную запись, не только общий домен."""
    p = urlsplit(core.url(address))
    host = lambda h: (h or '').lower().removeprefix('www.').replace('vk.com', 'vk.ru')
    targets = [source['profile_url']] + [s['url'] for s in source.get('seed_links', [])]
    for candidate in targets:
        q = urlsplit(candidate)
        if host(p.hostname) != host(q.hostname):
            continue
        if source['platform'] == 'forum':
            return True
        base = q.path.rstrip('/')
        if p.path.rstrip('/') == base or p.path.startswith(base + '/'):
            return True
    return False


def start(root, run, days=30):
    core.config(root)
    if type(days) is not int or not 1 <= days <= 90:
        raise core.MadError('Окно поиска: 1–90 дней')
    path = folder(root, run) / 'research.json'
    if path.exists():
        raise core.MadError('Исследование уже существует; файлы сохранены')
    data = {'schema_version': 1, 'id': run, 'created_at': core.utcnow(), 'checked_at': None,
        'period': [(today()-timedelta(days=days-1)).isoformat(), today().isoformat()],
        'coverage': [{'source_id': s['id'], 'status': 'not_checked', 'query': '',
                      'checked_at': None, 'note': '', 'evidence': None} for s in registry(root).values()],
        'observations': [], 'candidates': [],
        'analysis': {k: '' for k in ('summary', 'alternatives', 'unmet_needs', 'growth_assessment', 'sample_limits')}}
    core.save(path, data)
    return {'path': str(path), 'state': 'research_required', 'network_called': False,
            'next_step': 'Прочитайте источники средствами агента, сохраните заметки, затем research-check и plan-build.'}


def add_evidence(root, run, key, filename):
    core.ident(key)
    core.load(folder(root, run) / 'research.json')
    path = core.safe(root, f'content/research/{run}/evidence/{key}.txt')
    if path.exists():
        raise core.MadError('Заметка уже существует; не перезаписывать незаметно')
    src = Path(filename).absolute()
    if any(part.is_symlink() for part in (src, *src.parents)):
        raise core.MadError('Источник не должен быть символической ссылкой')
    raw = src.read_bytes()
    if not raw.strip() or len(raw) > 200000:
        raise core.MadError('Нужна разрешённая заметка до 200 КБ')
    core.write(path, raw.decode('utf-8-sig'))
    return {'path': path.relative_to(Path(root).resolve()).as_posix(), 'sha256': core.sha(path),
            'locator': '', 'note': 'Файл закреплён, но CLI не удостоверяет факт чтения оригинала.'}


def _evidence_paths(value):
    if isinstance(value, dict):
        if 'path' in value and 'sha256' in value:
            yield value['path']
        for v in value.values():
            yield from _evidence_paths(v)
    elif isinstance(value, list):
        for v in value:
            yield from _evidence_paths(v)


def fingerprint(root, run):
    path = folder(root, run) / 'research.json'
    report = core.load(path)
    parts = {'report': core.sha(path), 'policy': 'market-v1'}
    for rel in _evidence_paths(report):
        if not isinstance(rel, str) or not rel.startswith(f'content/research/{run}/evidence/'):
            raise core.MadError('Доказательство вне папки исследования')
        parts[rel] = core.sha(core.safe(root, rel))
    for name in ('community-sources.json', 'capabilities.json', 'problems.json'):
        parts[name] = core.knowledge(root, name)
    parts['config'] = core.config(root)
    return hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def independent_groups(rows, sources):
    """Перепечатки объединяются по издателю, первоисточнику и нормализованному URL."""
    components = []
    for row in rows:
        source = sources[row['source_id']]
        if row['status'] != 'read' or source['relationship'] != 'external':
            continue
        group = {'publisher:' + source['publisher_group'], 'origin:' + row['independence_key'],
                 'url:' + normalized_url(row['url'])}
        separate = []
        for previous in components:
            if group & previous:
                group |= previous
            else:
                separate.append(previous)
        components = separate + [group]
    return components


def check(root, run):
    errors = []
    items = []
    def need(condition, message):
        if not condition:
            raise core.MadError(message)
    def fresh(value):
        day = date.fromisoformat(value)
        need(0 <= (today()-day).days <= MAX_AGE_DAYS, 'Исследование/проверка старше 7 дней либо датированы будущим')
        return day
    def evidence(obj):
        need(isinstance(obj, dict) and bool(obj.get('locator')), 'Нужны заметка и точный раздел/сообщение')
        rel = obj['path']
        need(rel.startswith(f'content/research/{run}/evidence/'), 'Заметка вне evidence этого исследования')
        path = core.safe(root, rel)
        need(path.is_file() and path.stat().st_size <= 200000, 'Заметка отсутствует или превышает лимит')
        need(core.sha(path) == obj.get('sha256'), 'SHA256 заметки не совпадает')
        text = path.read_text(encoding='utf-8')
        need(bool(text.strip()), 'Пустая заметка')
        need(not any(x in text for x in ('ЗАПОЛНИТЬ', 'TODO', 'TBD')), 'В доказательстве остался шаблон')
        return text
    try:
        cfg = core.config(root)
        data = core.load(folder(root, run) / 'research.json')
        need(data.get('schema_version') == 1 and data.get('id') == run, 'Неверная схема исследования')
        reviewed = fresh(data['checked_at'])
        first, last = [date.fromisoformat(x) for x in data['period']]
        need(first <= last <= reviewed and 0 <= (last-first).days < 90, 'Некорректное окно исследования')
        need((reviewed-last).days <= MAX_AGE_DAYS, 'Окно поиска устарело: исследуйте текущую проблематику')
        need(all(isinstance(data.get('analysis', {}).get(k), str) and data['analysis'][k].strip()
                 for k in ('summary','alternatives','unmet_needs','growth_assessment','sample_limits')),
             'Сначала анализ проблем, попыток решения, альтернатив, незакрытых потребностей и ограничений выборки')
        for text in data['analysis'].values():
            need(not any(x in str(text) for x in ('ЗАПОЛНИТЬ', 'TODO', 'TBD')), 'Анализ содержит шаблон')
        reg = registry(root)
        cover = {}
        attempted = set()
        for row in data['coverage']:
            sid = row['source_id']
            need(sid in reg and sid not in cover, 'Повтор или неизвестный источник в coverage')
            cover[sid] = row
            need(row['status'] in STATUSES, 'Неизвестный статус чтения')
            if row['status'] == 'not_checked':
                continue
            need(fresh(row['checked_at']) <= reviewed, 'Проверка площадки позже отчёта')
            need(bool(row.get('query')) and bool(row.get('note')), 'Запишите фактический запрос и результат попытки')
            evidence(row['evidence'])
            attempted.add(reg[sid]['platform'])
        need(PLATFORMS <= attempted, 'До плана проверьте форумы, ВК, Instagram и TikTok; недоступность фиксируется, а не скрывается')
        problems = {p['id']: p for p in core.knowledge(root, 'problems.json')}
        caps = {c['id']: c for c in core.knowledge(root, 'capabilities.json')}
        obs = {}
        russian = False
        for row in data['observations']:
            oid = core.ident(row['id']); sid = row['source_id']
            need(oid not in obs and sid in reg and sid in cover, 'Неизвестный источник или повтор наблюдения')
            need(row['status'] in ('read','metadata_only'), 'Наблюдение требует read или metadata_only')
            need(fresh(row['read_at']) <= reviewed, 'Неверная дата чтения наблюдения')
            need(belongs(row['url'], reg[sid]), 'URL не относится к заявленному автору/сообществу')
            if row.get('occurred_at'):
                need(date.fromisoformat(row['occurred_at']) <= date.fromisoformat(row['read_at']), 'Событие позже чтения')
            need(row.get('problem_id') in problems, 'Новая проблема сначала регистрируется с подтверждённой возможностью')
            need(all(row.get(k) for k in ('problem','attempted_solution','outcome','independence_key')), 'Не описаны проблема, попытка, результат или происхождение обсуждения')
            need(row.get('outcome_status') in ('author_reported','suggested','unresolved','not_verified'), 'Не указан статус результата')
            need(row.get('public_or_redacted') is True, 'Нужны публичные/разрешённые обезличенные данные')
            evidence(row['evidence'])
            if row['status'] == 'read':
                need(cover[sid]['status'] == 'read', 'Нельзя считать материал прочитанным при metadata_only/blocked площадке')
                if reg[sid]['relationship'] == 'external':
                    russian = russian or reg[sid]['region'] == 'RU'
            obs[oid] = row
        if data['candidates']:
            need(len(independent_groups(list(obs.values()), reg)) >= 2 and russian, 'Для плана нужны прочитанные материалы двух независимых внешних источников, включая российский')
        seen = set()
        for candidate in data['candidates']:
            pid = candidate['problem_id']
            need(pid in problems and pid not in seen, 'Неизвестная/повторная тема')
            seen.add(pid)
            ids = candidate['observation_ids']
            need(isinstance(ids, list) and bool(ids) and len(ids) == len(set(ids)) and not set(ids)-obs.keys(), 'Тема без уникальных наблюдений')
            selected = [obs[i] for i in ids]
            need(all(o['problem_id'] == pid and o['status'] == 'read' and reg[o['source_id']]['relationship'] == 'external' for o in selected),
                 'Тема не подтверждена прочитанными внешними наблюдениями именно этой проблемы')
            need(candidate.get('reader_value') and candidate.get('priority_reason'), 'Нет пользы читателю или обоснования приоритета')
            expected = set(problems[pid]['capability_ids'])
            checked = set()
            for proof in candidate['solution_checks']:
                cid = proof['capability_id']
                need(cid in expected and cid not in checked, 'Решение не соответствует проблеме либо продублировано')
                need(caps[cid]['status'] in ('documented','conditional','tested'), 'Возможность не подтверждена')
                need(proof['url'].split('#')[0] in caps[cid]['source_urls'], 'Форум не заменяет первичную документацию решения MAD-auto')
                need(fresh(proof['checked_at']) <= reviewed, 'Неверная дата проверки решения')
                evidence(proof['evidence']); checked.add(cid)
            need(checked == expected, 'До плана проверьте все используемые возможности MAD-auto')
            measurement = candidate.get('trend_measurement')
            trend = {'status': 'not_measured'}
            if measurement is not None:
                need(measurement['baseline']['source'] != 'synthetic', 'Синтетические числа не являются рыночным трендом')
                measured = json.loads(evidence(candidate['trend_evidence']))
                need(measured == measurement, 'Измерения не совпадают с закреплённой выгрузкой')
                need(measurement['current']['end'] == last.isoformat(), 'Измерение не покрывает актуальное окно исследования')
                trend = measured_trend(measurement)
            current = [o for o in selected if o.get('occurred_at') and first <= date.fromisoformat(o['occurred_at']) <= last]
            publisher_count = len(independent_groups(selected, reg))
            old_url = problems[pid].get('existing_url')
            items.append({'problem_id':pid,'title':problems[pid]['question'],
                'action':'update' if old_url else 'new','existing_url':old_url,
                'observation_ids':ids,'source_urls':list(dict.fromkeys(o['url'] for o in selected)),
                'capability_ids':sorted(expected),'reader_value':candidate['reader_value'],
                'priority_reason':candidate['priority_reason'],'priority':min(publisher_count,3)*10+bool(current)*5,
                'demand':'observed_interest' if current else 'historical_or_undated_problem',
                'trend':trend,'limitations':list(dict.fromkeys(lim for cid in expected for lim in caps[cid]['limitations']))})
        items.sort(key=lambda item:(-item['priority'],item['problem_id']))
    except (core.MadError, KeyError, TypeError, ValueError, AttributeError, OSError) as exc:
        errors.append({'code':'market_research','message':str(exc) if isinstance(exc,core.MadError) else 'Неполный отчёт исследования или отсутствующий файл'})
    return {'ok':not errors,'errors':errors,'items':items if not errors else [],
            'network_called':False,'note':'Проверяется полнота и связность доказательств, не истинность и не сам факт работы браузера. Тренд без измерения не заявляется.'}


def expected_plan(root, run):
    result = check(root, run)
    if not result['ok']:
        raise core.MadError(result['errors'][0]['message'])
    return {'schema_version':1,'research_id':run,'research_hash':fingerprint(root,run),'items':result['items']}


def build_plan(root, run):
    plan = expected_plan(root, run)
    dest = core.safe(root, 'content/plans/' + core.ident(run) + '.json')
    core.save(dest, plan)
    lines = ['# Контент-план MAD-auto', '', 'Исследование: '+run+'. Это редакционный приоритет, не измеренная частотность.', '']
    for item in plan['items']:
        lines.extend(['## '+item['title'], 'Действие: '+item['action']+'; спрос: '+item['demand']+'; тренд: '+item['trend']['status']+'.',
                      item['reader_value'], item['priority_reason'], 'Источники: '+', '.join(item['source_urls']), ''])
    if not plan['items']:
        lines.append('Подтверждённых тем нет. Статьи не создавать; не выдумывать находки ради плана.')
    core.write(dest.with_suffix('.md'), '\n'.join(lines)+'\n')
    return {'path':str(dest),'items':len(plan['items']),'research_hash':plan['research_hash'],'network_called':False}


def require_plan(root, run, problem_id):
    if not run:
        raise core.MadError('Сначала research-new → исследование → research-check → plan-build; укажите --research')
    plan = core.load(core.safe(root, 'content/plans/' + core.ident(run) + '.json'))
    if plan != expected_plan(root,run):
        raise core.MadError('Контент-план изменён или устарел; повторите исследование и plan-build')
    selected = next((i for i in plan['items'] if i['problem_id'] == problem_id),None)
    if selected is None:
        raise core.MadError('Проблема отсутствует в проверенном контент-плане')
    return plan, selected


def link_job(root, name, run):
    path = core.jobdir(root,name)/'brief.json'
    brief = core.load(path)
    plan,item = require_plan(root,run,brief['problem_id'])
    brief['market_research'] = {'id':run,'hash':plan['research_hash']}
    core.save(path,brief)
    return {'job':name,'research_id':run,'approval':'requires_recheck'}


def validate_job(root, name):
    try:
        brief = core.load(core.jobdir(root,name)/'brief.json')
        link = brief.get('market_research',{})
        plan,item = require_plan(root,link.get('id'),brief.get('problem_id'))
        if link.get('hash') != plan['research_hash']:
            raise core.MadError('Исследование изменено после подготовки статьи: повторная проверка и research-link обязательны')
        return []
    except (core.MadError,KeyError,TypeError,ValueError,OSError) as exc:
        return [{'code':'market_research','message':str(exc) if isinstance(exc,core.MadError) else 'Нет актуального исследования'}]
