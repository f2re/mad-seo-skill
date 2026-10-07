"""Сигналы спроса, воспроизводимый отбор ниш и импорт фактических метрик."""
from __future__ import annotations

import csv
import json
import math
import sqlite3
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .core import MadError, ident, knowledge, load, safe, save, url


def normalized_url(value):
    p = urlsplit(url(value))
    query = urlencode(sorted((k,v) for k,v in parse_qsl(p.query) if not k.lower().startswith('utm_')))
    return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip('/') or '/', query, ''))


def import_signals(root, filename):
    incoming = load(filename)
    if not isinstance(incoming,list):
        raise MadError('Сигналы должны быть массивом JSON')
    problems = {x['id'] for x in knowledge(root,'problems.json')}
    destination = safe(root,'content/signals/observations.json')
    rows = load(destination) if destination.exists() else []
    keyed = {(r['problem_id'], normalized_url(r['url']), r['occurred_at']):r for r in rows}
    for r in incoming:
        ident(r['id'])
        if r.get('problem_id') not in problems:
            raise MadError('Сигнал вне зарегистрированных проблем MAD-auto')
        url(r['url'])
        observed = date.fromisoformat(r['observed_at'])
        occurred = date.fromisoformat(r['occurred_at']) if r.get('occurred_at') else None
        if observed > date.today() or (occurred and (occurred > observed or occurred > date.today())):
            raise MadError('Некорректная дата сигнала')
        if r.get('kind') not in ('forum','support','official-faq','release','search-console'):
            raise MadError('Неизвестный тип источника')
        if not r.get('evidence') or not r.get('attempted_solution') or not r.get('independence_key'):
            raise MadError('Нужны фактическая проблема, попытка решения и ключ независимости')
        if r.get('public_or_redacted') is not True:
            raise MadError('Не публикуйте переписку, VIN, номера, адреса и серийные номера')
        # observed_at is NEVER substituted for an unknown event date.
        keyed[(r['problem_id'], normalized_url(r['url']), r.get('occurred_at'))] = r
    save(destination,list(keyed.values()))
    return {'records':len(keyed),'network_called':False}


def search_plan(root):
    plans=[]
    for p in knowledge(root,'problems.json'):
        plans.append({'problem_id':p['id'],'question':p['question'],'queries':p['search_queries'],
                      'source_priority':['публичные обращения пользователей','профильные форумы','документация MAD-auto','собственные выгрузки поиска'],
                      'record':['url','occurred_at','observed_at','evidence','attempted_solution','independence_key'],
                      'existing_url':p.get('existing_url')})
    from .market import registry
    return {'plans':plans,'search_executed':False,'sources':list(registry(root).values()),
            'required_before_article':'research-new → фактический поиск и чтение → research-check → plan-build → new --research',
            'instruction':'Это задания исследователю с веб-поиском, а не найденные сигналы. Откройте первоисточник; закрытый форум и сниппет не считайте прочитанными.'}


def rank(root, as_of=None, days=30):
    end = date.fromisoformat(as_of) if as_of else date.today()
    if days < 1 or days > 366 or end > date.today():
        raise MadError('Нужно окно 1–366 дней без будущих дат')
    start = end-timedelta(days=days-1)
    path=safe(root,'content/signals/observations.json')
    signals=load(path) if path.exists() else []
    result=[]
    caps={x['id']:x for x in knowledge(root,'capabilities.json')}
    for p in knowledge(root,'problems.json'):
        fits=[caps[c] for c in p['capability_ids'] if c in caps and caps[c]['status'] in ('documented','conditional','tested')]
        if not fits:
            continue
        all_matches=[s for s in signals if s['problem_id']==p['id']]
        current=[s for s in all_matches if s.get('occurred_at') and start <= date.fromisoformat(s['occurred_at']) <= end and date.fromisoformat(s['observed_at']) <= end]
        independent={s['independence_key'] for s in current if s['kind'] in ('forum','support','search-console')}
        score=40+min(len(independent),3)*15+(5 if not p.get('existing_url') else 0)
        result.append({'problem_id':p['id'],'title':p['question'],'priority_score':score,
            'score_meaning':'Редакционный приоритет, не частотность запроса и не вероятность продажи',
            'status':'observed_interest' if independent else 'documentation_hypothesis',
            'independent_signals':len(independent),'source_urls':[s['url'] for s in current],
            'trend':'not_measured','action':'update' if p.get('existing_url') else 'research_then_write',
            'existing_url':p.get('existing_url'),'capability_ids':[c['id'] for c in fits]})
    return {'period':[start.isoformat(),end.isoformat()],'topics':sorted(result,key=lambda x:(-x['priority_score'],x['problem_id'])),
            'note':'Число найденных обсуждений не равно распространённости проблемы. Без сопоставимых измерений роста нет.'}


def measured_trend(data):
    """Два полных одинаковых окна одного источника. Пороги — редакционная политика."""
    try:
        a,b=data['baseline'],data['current']
        if any(w.get('complete') is not True for w in (a,b)):
            return {'status':'insufficient_data'}
        if any(a[k]!=b[k] for k in ('source','unit','scope','days')) or a['days']<=0:
            return {'status':'incomparable'}
        for w in (a,b):
            if isinstance(w['value'],bool) or not isinstance(w['value'],(int,float)) or not math.isfinite(w['value']) or w['value']<0:
                raise MadError('Неверное измеренное значение')
        for w in (a,b):
            first,last=date.fromisoformat(w['start']),date.fromisoformat(w['end'])
            if (last-first).days+1!=w['days'] or last>date.today():
                return {'status':'incomparable'}
        if date.fromisoformat(a['end'])+timedelta(days=1)!=date.fromisoformat(b['start']):
            return {'status':'incomparable','reason':'Нужны соседние непересекающиеся окна'}
        if a['value'] < 20 or b['value'] < 20:
            return {'status':'insufficient_data','reason':'Малая база; рост в процентах не рассчитывается'}
        ratio=b['value']/a['value']
        return {'status':'rising' if ratio>=1.25 else 'falling' if ratio<=0.8 else 'stable',
                'baseline':a['value'],'current':b['value'],'relative_change':ratio-1,
                'note':'Наблюдаемое изменение, не доказательство причины и не прогноз.'}
    except (KeyError,TypeError):
        raise MadError('Нужны baseline/current: source, unit, scope, start, end, days, complete, value')


def analytics_import(root, filename, provider):
    """Нормализованный CSV: date,page,query,clicks,impressions. Без выдуманных нулей."""
    if provider not in ('google','yandex','other'):
        raise MadError('Неизвестный источник аналитики')
    parsed=[]
    with Path(filename).open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if not {'date','page','query','clicks','impressions'} <= set(reader.fieldnames or []):
            raise MadError('CSV: date,page,query,clicks,impressions')
        for r in reader:
            day=date.fromisoformat(r['date'])
            if day>date.today():
                raise MadError('Метрики из будущего')
            url(r['page'])
            values=[]
            for field in ('clicks','impressions'):
                value=int(r[field]) if r[field].strip() else None
                if value is not None and value<0:
                    raise MadError('Отрицательная метрика')
                values.append(value)
            if all(v is not None for v in values) and values[0]>values[1]:
                raise MadError('Клики больше показов: проверьте источник и единицу наблюдения')
            parsed.append((provider,day.isoformat(),r['page'],r['query'],*values))
    database=safe(root,'analytics/metrics.sqlite3');database.parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(database)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS metrics (source TEXT,date TEXT,page TEXT,query TEXT,clicks INTEGER,impressions INTEGER,PRIMARY KEY(source,date,page,query))')
        db.executemany('INSERT INTO metrics VALUES(?,?,?,?,?,?) ON CONFLICT(source,date,page,query) DO UPDATE SET clicks=excluded.clicks,impressions=excluded.impressions',parsed)
        db.commit()
    return {'imported':len(parsed),'provider':provider,'idempotent':True}


def analytics_report(root):
    path=safe(root,'analytics/metrics.sqlite3')
    if not path.exists():
        return {'status':'no_data','actions':[]}
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        rows=db.execute('SELECT source,page,MIN(date),MAX(date),SUM(clicks),SUM(impressions),COUNT(*),COUNT(clicks),COUNT(impressions) FROM metrics GROUP BY source,page ORDER BY SUM(impressions) DESC').fetchall()
    records=[]
    for source,page,first,last,clicks,impressions,n,nc,ni in rows:
        complete=nc==ni==n
        records.append({'source':source,'page':page,'first_date':first,'last_date':last,
            'observed_clicks':clicks,'observed_impressions':impressions,
            'metric_fields_complete':complete,'ctr':clicks/impressions if complete and impressions else None,
            'calendar_coverage':'not_inferred','query_rows':n})
    return {'status':'available','pages':records,
        'note':'Даты отражают выгрузку. Покрытие всех дней/запросов не предполагается. Причинность, рост спроса и доля ИИ из этих сумм не выводятся.'}
