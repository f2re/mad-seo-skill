"""Командная строка. Никаких скрытых запросов к модели или публикации на сайт."""
from __future__ import annotations

import argparse
import json
import os
import sys
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import core, render, research


@contextmanager
def lock(root):
    path = core.safe(root, '.mad/workspace.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise core.MadError('Рабочая папка занята. После аварии проверьте процесс в .mad/workspace.lock') from exc
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(str(os.getpid()))
        yield
    finally:
        path.unlink(missing_ok=True)


def parser():
    p = argparse.ArgumentParser(description='MAD-auto: проблема → доказанное решение → статья → проверка')
    p.add_argument('--workspace', type=Path, default=Path.cwd())
    p.add_argument('--version', action='version', version=core.VERSION)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    sub.add_parser('doctor')
    sub.add_parser('search-plan')
    n = sub.add_parser('new')
    n.add_argument('slug'); n.add_argument('--problem',required=True); n.add_argument('--topic')
    n.add_argument('--research',required=True,help='ID актуального исследования с контент-планом')
    for command in ('validate','status','review-template'):
        sub.add_parser(command).add_argument('slug')
    n=sub.add_parser('export');n.add_argument('slug');n.add_argument('--approved',action='store_true')
    n=sub.add_parser('approve');n.add_argument('slug');n.add_argument('--confirm',required=True)
    n=sub.add_parser('source-add');n.add_argument('slug');n.add_argument('--id',required=True)
    for arg in ('url','title','file','locator'):
        n.add_argument('--'+arg,required=True)
    n.add_argument('--kind',choices=['official','forum','expert','analytics'],required=True)
    n=sub.add_parser('signals-import');n.add_argument('--file',type=Path,required=True)
    n=sub.add_parser('topics');n.add_argument('--as-of');n.add_argument('--days',type=int,default=30)
    n=sub.add_parser('trend-check');n.add_argument('--file',type=Path,required=True)
    n=sub.add_parser('analytics-import');n.add_argument('--file',type=Path,required=True);n.add_argument('--provider',required=True,choices=['google','yandex','other'])
    sub.add_parser('analytics-report')
    sub.add_parser('knowledge-check')
    n=sub.add_parser('install');n.add_argument('--target',type=Path,required=True);n.add_argument('--dry-run',action='store_true')
    sub.add_parser('sources',help='Сообщества и авторы: реестр, не выполненный поиск')
    n=sub.add_parser('research-new');n.add_argument('run');n.add_argument('--days',type=int,default=30)
    for command in ('research-check','plan-build'):
        sub.add_parser(command).add_argument('run')
    n=sub.add_parser('research-evidence');n.add_argument('run');n.add_argument('--key',required=True);n.add_argument('--file',type=Path,required=True)
    n=sub.add_parser('research-link');n.add_argument('slug');n.add_argument('--research',required=True)
    return p


def knowledge_check(root):
    sources=core.knowledge(root,'sources.json'); caps=core.knowledge(root,'capabilities.json'); problems=core.knowledge(root,'problems.json')
    for entries in (sources,caps,problems):
        if len(entries)!=len({x['id'] for x in entries}):
            raise core.MadError('Повтор id в базе знаний')
    sids={s['id'] for s in sources};cids={c['id'] for c in caps}
    for cap in caps:
        if not cap.get('source_ids') or set(cap['source_ids'])-sids or not cap.get('limitations'):
            raise core.MadError('Возможность без первоисточника или ограничений')
        for address in cap['source_urls']:
            core.url(address)
    for problem in problems:
        if not problem.get('capability_ids') or set(problem['capability_ids'])-cids:
            raise core.MadError('Проблема без поддерживаемого решения')
    from .market import registry
    communities = registry(root)
    return {'ok':True,'sources':len(sources),'capabilities':len(caps),'problems':len(problems),
            'community_sources':len(communities),
            'open_conflicts':len([c for c in core.knowledge(root,'conflicts.json') if c['status']=='open'])}


def dispatch(args):
    root=args.workspace.resolve();cmd=args.command
    if cmd=='install':
        from .install import install
        return install(args.target.resolve(),args.dry_run)
    if cmd=='init':
        return core.init(root)
    if cmd=='doctor':
        return {'version':core.VERSION,'python':sys.version.split()[0],
            'initialized':core.safe(root,'mad.json').exists(), 'network_called':False,
            'model_called':False, 'cms_api':'not_connected',
            'next_step':'python mad.py init' if not core.safe(root,'mad.json').exists() else 'python mad.py sources; python mad.py research-new first-research',
            'note':'Наличие адаптеров не доказывает запуск субагентов или авторизацию внешних сервисов.'}
    core.config(root)
    from . import market
    if cmd=='sources': return {'sources':list(market.registry(root).values()),'search_executed':False}
    if cmd=='research-check': return market.check(root,args.run)
    if cmd=='search-plan': return research.search_plan(root)
    if cmd=='knowledge-check': return knowledge_check(root)
    if cmd=='topics': return research.rank(root,args.as_of,args.days)
    if cmd=='trend-check':
        data=core.load(args.file)
        return {**research.measured_trend(data),'input_note':data.get('note'),
                'synthetic':data.get('baseline',{}).get('source')=='synthetic'}
    if cmd=='analytics-report': return research.analytics_report(root)
    if cmd=='validate': return core.validate(root,args.slug)
    if cmd=='status':
        report=core.validate(root,args.slug)
        result={'validation':report,'approval':'missing_or_stale'}
        if report['ok']:
            result['confirmation_token']=args.slug+'@'+core.snapshot(root,args.slug)
            try:
                core.require_approval(root,args.slug);result['approval']='current'
            except core.MadError:
                pass
        return result
    with lock(root):
        if cmd=='research-new': return market.start(root,args.run,args.days)
        if cmd=='research-evidence': return market.add_evidence(root,args.run,args.key,args.file)
        if cmd=='research-link': return market.link_job(root,args.slug,args.research)
        if cmd=='plan-build': return market.build_plan(root,args.run)
        if cmd=='new':
            return core.new(root,args.slug,args.topic or next((p['question'] for p in core.knowledge(root,'problems.json') if p['id']==args.problem),args.problem),args.problem,args.research)
        if cmd=='source-add': return core.source_add(root,args.slug,args.id,args.url,args.title,args.file,args.locator,args.kind)
        if cmd=='review-template': return core.review_template(root,args.slug)
        if cmd=='approve': return core.approve(root,args.slug,args.confirm)
        if cmd=='export': return render.export(root,args.slug,args.approved)
        if cmd=='signals-import': return research.import_signals(root,args.file)
        if cmd=='analytics-import': return research.analytics_import(root,args.file,args.provider)
    raise core.MadError('Неизвестная команда')


def main(argv=None):
    if sys.version_info<(3,10):
        print('Требуется Python 3.10+',file=sys.stderr);return 2
    try:
        result=dispatch(parser().parse_args(argv))
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
        return 1 if result.get('ok') is False else 0
    except (core.MadError,OSError,KeyError,TypeError,ValueError,AttributeError,sqlite3.Error) as exc:
        print(json.dumps({'error':str(exc) if isinstance(exc,core.MadError) else 'Некорректные данные или файловая ошибка'},ensure_ascii=False),file=sys.stderr)
        return 2
