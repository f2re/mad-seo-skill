"""Файлы, проверка доказательств и ручное утверждение редакционного пакета."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

ENGINE = Path(__file__).resolve().parent.parent
CHECKS = ('facts', 'compatibility', 'safety', 'usefulness', 'voice', 'seo', 'privacy', 'visuals')
VERSION = '1.1.0'


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class MadError(ValueError):
    """Ошибка входных данных без секретов и сетевых ответов."""


def ident(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', value) or len(value) > 80:
        raise MadError('Идентификатор: до 80 строчных латинских букв, цифр и дефисов')
    return value


def safe(root, relative):
    root = Path(root).resolve()
    rel = Path(relative)
    if rel.is_absolute() or '..' in rel.parts or '\\' in str(relative):
        raise MadError('Путь выходит за пределы рабочей папки')
    result = root
    for part in rel.parts:
        result = result / part
        if result.is_symlink():
            raise MadError('Символические ссылки не разрешены')
    return result


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise MadError('Повторный ключ JSON: ' + key)
        result[key] = value
    return result


def load(path):
    if Path(path).is_symlink():
        raise MadError('Символическая ссылка вместо JSON')
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=unique_pairs,
                          parse_constant=lambda value: (_ for _ in ()).throw(MadError('NaN/Infinity запрещены')))
    except (OSError, json.JSONDecodeError) as exc:
        raise MadError('Не читается JSON: ' + Path(path).name) from exc


def write(path, text):
    path = Path(path)
    if path.is_symlink():
        raise MadError('Нельзя записывать через символическую ссылку')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.mad-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def save(path, value):
    write(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def sha(path):
    if Path(path).is_symlink():
        raise MadError('Символическая ссылка вместо источника')
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def url(value):
    if not isinstance(value, str):
        raise MadError('URL должен быть строкой')
    p = urlsplit(value)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or any(ord(c) < 33 for c in value):
        raise MadError('Нужен HTTPS URL без пароля и пробелов')
    if any(k.lower() in ('token','access_token','api_key','password','secret') for k,v in parse_qsl(p.query) if v):
        raise MadError('Секрет в публичном URL')
    return value


def config(root):
    data = load(safe(root, 'mad.json'))
    if data.get('schema_version') != 1:
        raise MadError('mad.json: ожидается schema_version=1')
    url(data.get('site_url'))
    return data


def knowledge(root, filename):
    local = safe(root, 'knowledge/' + filename)
    return load(local if local.exists() else ENGINE / 'knowledge' / filename)


def init(root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = safe(root, 'mad.json')
    if path.exists():
        config(root)
        return {'status': 'exists', 'changed': False}
    save(path, {'schema_version': 1, 'brand': 'MAD-auto', 'language': 'ru',
                'site_url': 'https://m.wifiobd.ru', 'article_path': '/blog/',
                'publication': 'manual-cms-import', 'max_parallel_agents': 3})
    for folder in ('content/jobs', 'content/signals', 'content/voice', 'analytics', 'exports'):
        safe(root, folder).mkdir(parents=True, exist_ok=True)
    return {'status': 'created', 'network_called': False}


def jobdir(root, name):
    return safe(root, 'content/jobs/' + ident(name))


def new(root, name, topic, problem_id, research_id=None):
    from .market import require_plan
    plan, selected = require_plan(root, research_id, problem_id)
    cfg = config(root)
    ident(name)
    problems = {p['id']: p for p in knowledge(root, 'problems.json')}
    if problem_id not in problems:
        raise MadError('Сначала добавьте доказанную проблему в knowledge/problems.json')
    problem = problems[problem_id]
    job = jobdir(root, name)
    if job.exists():
        raise MadError('Задание уже существует; файлы не перезаписаны')
    existing = problem.get('existing_url')
    target = existing or cfg['site_url'].rstrip('/') + cfg['article_path'] + name
    save(job / 'brief.json', {'schema_version': 1, 'slug': name, 'topic': topic, 'problem_id': problem_id,
        'intent': problem['question'], 'audience': 'владелец устройства',
        'market_research': {'id': research_id, 'hash': plan['research_hash']},
        'problem_source_ids': [], 'capability_ids': problem['capability_ids'],
        'solution_status': 'documented', 'scope_mode': 'general',
        'scope': {k: None for k in ('ecu', 'ecu_software', 'adapter', 'adapter_firmware', 'application', 'application_version', 'platform')},
        'limitations': list(selected['limitations']), 'risk': 'low', 'added_value': selected['reader_value'],
        'seo': {'action': 'update' if existing else 'new', 'target_url': target,
                'existing_urls': [existing] if existing else [], 'reason': ''}})
    save(job / 'sources.json', [])
    save(job / 'claims.json', [])
    save(job / 'pack.json', {'schema_version': 1, 'title': topic, 'description': '', 'summary': '',
        'summary_claim_ids': [], 'sections': [], 'visuals': [],
        'author': {'name': '', 'url': ''}, 'date_published': None, 'date_modified': None,
        'cta': 'Сверьте модель ЭБУ и версию ПО с документацией перед выбором режима.'})
    write(job / 'research.md', '# Исследование\n\nСначала сохраните источники проблемы и решения. Не заполняйте спрос по догадке.\n')
    return {'job': name, 'path': str(job), 'state': 'needs_evidence', 'network_called': False}


def snapshot(root, name):
    job = jobdir(root, name)
    files = [safe(root, 'mad.json')]
    files += [job / name for name in ('brief.json', 'pack.json', 'sources.json', 'claims.json')]
    for source in load(job / 'sources.json'):
        files.append(safe(root, source['path']))
    for visual in load(job / 'pack.json').get('visuals', []):
        files.append(safe(root, visual['path']))
    hashes = {str(p.relative_to(Path(root).resolve())): sha(p) for p in files}
    market = load(job / 'brief.json').get('market_research')
    if market:
        from .market import fingerprint
        hashes['market/research'] = fingerprint(root, market['id'])
        hashes['market/plan'] = sha(safe(root, 'content/plans/' + ident(market['id']) + '.json'))
    for folder in ('mad', 'agents', 'skills', 'docs', 'knowledge', 'schemas'):
        base = ENGINE / folder
        for path in sorted(base.rglob('*')):
            if path.is_file() and path.suffix in ('.py', '.md', '.json'):
                hashes['engine/' + str(path.relative_to(ENGINE))] = sha(path)
    local_knowledge = safe(root, 'knowledge')
    if local_knowledge.exists():
        for p in sorted(local_knowledge.rglob('*.json')):
            hashes['workspace/' + str(p.relative_to(root))] = sha(safe(root, p.relative_to(root)))
    for p in safe(root, 'content/voice').glob('*.md'):
        hashes[str(p.relative_to(root))] = sha(safe(root, p.relative_to(root)))
    for name in ('AGENTS.md','CLAUDE.md','GEMINI.md'):
        for prefix,base in (('engine/',ENGINE),('workspace/',Path(root))):
            p=safe(base,name)
            if p.exists():
                hashes[prefix+name]=sha(p)
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()


def source_add(root, name, source_id, source_url, title, filename, locator, kind):
    ident(source_id)
    url(source_url)
    if kind not in ('official', 'forum', 'analytics', 'expert'):
        raise MadError('kind: official/forum/analytics/expert')
    text = Path(filename).read_text(encoding='utf-8')
    if not text.strip() or len(text.encode()) > 200000:
        raise MadError('Нужна разрешённая выдержка или фактологическая заметка до 200 КБ')
    job = jobdir(root, name)
    sources = load(job / 'sources.json')
    if any(s['id'] == source_id for s in sources):
        raise MadError('Источник с таким id уже существует')
    relative = f'content/jobs/{name}/evidence/{source_id}.txt'
    write(safe(root, relative), text)
    record = {'id': source_id, 'url': source_url, 'title': title, 'kind': kind,
              'visibility': 'public', 'verified_at': date.today().isoformat(),
              'locator': locator, 'path': relative, 'sha256': sha(safe(root, relative))}
    sources.append(record)
    save(job / 'sources.json', sources)
    return {'source': source_id, 'network_called': False,
            'note': 'Файл закреплён; чтение оригинала и права проверяет исследователь, не CLI.'}


CLICHES = ('в современном мире', 'откройте для себя', 'незаменимый помощник',
           'революционный прорыв', 'новый уровень диагностики', 'идеальное решение для каждого',
           'непревзойдённое качество', 'вы не поверите')
UNIVERSAL = re.compile(r'(?:подходит|совместим\w*|работает)\s+(?:(?:с|для|на)\s+)?(?:люб\w*|все\w*)\s+(?:авто\w*|эбу|контроллер\w*)', re.I)
UNSAFE = re.compile(r'(?:отключите|отключить)\s+(?:полностью\s+)?(?:брандмауэр|антивирус)|crack/|кряк|обход\w* лиценз', re.I)
NUMBERS = re.compile(r'(?<!\w)\d+(?:[.,]\d+)?\s*(?:мс|мА|ГБ|Гб|МБ|мм|см|км|мл|В\b|вольт\w*|%|об/мин|AFR\b|°[CС])', re.I)


def validate(root, name):
    errors, warnings = [], []
    def fail(code, text):
        errors.append({'code': code, 'message': text})
    try:
        cfg = config(root)
        job = jobdir(root, name)
        brief, sources, claims, pack = [load(job / f) for f in ('brief.json', 'sources.json', 'claims.json', 'pack.json')]
        if brief.get('schema_version') != 1 or pack.get('schema_version') != 1 or brief.get('slug') != name:
            fail('schema', 'Версия схемы или slug не совпадает')
        problems = {x['id']: x for x in knowledge(root, 'problems.json')}
        caps = {x['id']: x for x in knowledge(root, 'capabilities.json')}
        problem = problems.get(brief.get('problem_id'))
        if not problem:
            fail('problem', 'Нет зарегистрированной нишевой проблемы')
        if not brief.get('intent') or not brief.get('added_value'):
            fail('usefulness', 'Нужны задача читателя и добавленная польза относительно документации')
        requested = brief.get('capability_ids', [])
        if not requested or set(requested) - caps.keys():
            fail('solution', 'Нет подтверждённой возможности MAD-auto')
        if problem and set(requested) - set(problem['capability_ids']):
            fail('fit', 'Возможность не решает эту зарегистрированную проблему')
        if brief.get('solution_status') not in ('documented', 'tested', 'conditional'):
            fail('solution', 'Решение не подтверждено даже документацией')
        if brief.get('scope_mode') not in ('general', 'exact'):
            fail('scope', 'Область применимости: general или exact')
        if not isinstance(brief.get('limitations'), list) or not brief['limitations']:
            fail('limits', 'Явно опишите ограничения решения')
        if brief.get('scope_mode') == 'exact' and any(not brief.get('scope', {}).get(k) for k in ('ecu','ecu_software','adapter','adapter_firmware','application','application_version','platform')):
            fail('compatibility', 'Точная совместимость требует всей связки ЭБУ—ПО—адаптер—прошивка—приложение—платформа')
        if brief.get('risk') not in ('low', 'medium', 'high'):
            fail('risk', 'Риск должен быть low/medium/high')
        seo = brief.get('seo', {})
        target = url(seo.get('target_url'))
        if urlsplit(target).netloc != urlsplit(cfg['site_url']).netloc or not urlsplit(target).path.startswith(cfg['article_path']):
            fail('canonical', 'Статья должна иметь канонический URL на выбранном сайте в разделе /blog/')
        if urlsplit(target).query or urlsplit(target).fragment:
            fail('canonical', 'Канонический адрес не должен содержать параметры или якорь')
        if seo.get('action') not in ('new', 'update', 'merge'):
            fail('intent', 'Укажите new/update/merge')
        existing = problem.get('existing_url') if problem else None
        if existing and (seo.get('action') == 'new' or existing not in seo.get('existing_urls', [])):
            fail('duplicate', 'Проблему уже покрывает статья: сначала обновление или объединение')
        if seo.get('action') in ('update', 'merge') and (not seo.get('existing_urls') or not seo.get('reason')):
            fail('duplicate', 'Для обновления нужны существующие URL и причина')
        registry = {}
        for s in sources:
            sid = ident(s['id'])
            if sid in registry:
                fail('source_duplicate', sid)
            registry[sid] = s
            url(s['url'])
            verified = date.fromisoformat(s['verified_at'])
            if verified > date.today():
                fail('future_source', 'Дата проверки источника в будущем')
            if (date.today() - verified).days > 180:
                fail('stale_source', 'Источник старше 180 дней: перепроверьте ' + sid)
            if s.get('kind') not in ('official','expert','forum','analytics') or s.get('visibility') != 'public':
                fail('source_kind', 'Источник должен быть публичным или предварительно обезличенным с разрешением')
            if not s.get('locator') or not s.get('title'):
                fail('source_locator', 'У источника нет заголовка/точного раздела')
            path = safe(root, s['path'])
            if not str(s['path']).startswith(f'content/jobs/{name}/evidence/') or sha(path) != s.get('sha256'):
                fail('source_hash', 'Источник изменён или не закреплён внутри evidence: ' + sid)
            if not path.read_text(encoding='utf-8').strip():
                fail('source_empty', 'Пустое доказательство')
        official_urls = {s['url'].split('#')[0] for s in sources if s.get('kind') == 'official'}
        for cap_id in requested:
            if cap_id in caps and not official_urls.intersection(caps[cap_id]['source_urls']):
                fail('capability_source', 'Нет первичной документации выбранной возможности: ' + cap_id)
        demand = brief.get('problem_source_ids', [])
        if not demand or set(demand) - registry.keys():
            fail('problem_evidence', 'Нужны прочитанные источники самой проблемы; поисковая фраза не доказательство спроса')
        facts = {}
        for c in claims:
            cid = ident(c['id'])
            if cid in facts:
                fail('claim_duplicate', cid)
            facts[cid] = c
            if c.get('status') != 'verified' or not c.get('text') or not c.get('checked_by'):
                fail('claim', 'Непроверенное утверждение: ' + cid)
            sids = c.get('source_ids', [])
            if not sids or set(sids) - registry.keys():
                fail('claim_source', 'Неизвестный источник утверждения: ' + cid)
            if not any(registry[s].get('kind') in ('official','expert') for s in sids if s in registry):
                fail('primary', 'Форум доказывает проблему, но не техническую возможность устройства')
            if c.get('kind') not in ('capability','procedure','compatibility','limitation','measurement'):
                fail('claim_kind', 'Укажите вид утверждения: ' + cid)
            if c.get('kind') in ('compatibility','measurement'):
                if brief.get('scope_mode') != 'exact' or c.get('scope') != brief.get('scope'):
                    fail('claim_scope', 'Замер/совместимость не связаны с точной проверенной конфигурацией')
        def linked(text, ids):
            if not isinstance(text, str) or not text.strip() or not ids or set(ids) - facts.keys():
                fail('unlinked', 'Публичный блок без текста или связанных фактов')
                return
            supported = ' '.join(facts[i]['text'] for i in ids if i in facts)
            norm = lambda x: re.sub(r'\s+', '', x).replace(',', '.').lower()
            allowed = {norm(x) for x in NUMBERS.findall(supported)}
            if any(norm(x) not in allowed for x in NUMBERS.findall(text)):
                fail('numeric', 'Числовая характеристика отсутствует в связанных фактах')
        linked(pack.get('summary'), pack.get('summary_claim_ids', []))
        sections = pack.get('sections', [])
        roles = set()
        for section in sections:
            roles.add(section.get('role'))
            if not section.get('heading'):
                fail('heading', 'Раздел без заголовка')
            linked(section.get('text'), section.get('claim_ids', []))
        if not {'scope','requirements','steps','result','troubleshooting','limitations'} <= roles:
            fail('structure', 'Нужны применимость, подготовка, шаги, результат, ошибки и ограничения')
        if not pack.get('title') or not pack.get('description') or not pack.get('cta'):
            fail('metadata', 'Нужны заголовок, описание и полезный следующий шаг')
        for visual in pack.get('visuals', []):
            p = safe(root, visual['path'])
            if not visual['path'].startswith(f'content/jobs/{name}/media/') or p.suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):
                fail('visual', 'Изображения: PNG/JPG/WebP внутри media этого задания')
            if visual.get('kind') not in ('photo','screenshot','diagram') or visual.get('rights_confirmed') is not True or visual.get('privacy_checked') is not True:
                fail('visual_rights', 'Проверьте происхождение, права и персональные данные изображения')
            if not visual.get('alt') or not visual.get('caption') or sha(p) != visual.get('sha256'):
                fail('visual_hash', 'У изображения нет подписи, alt или совпадающего SHA256')
        if not pack.get('visuals'):
            warnings.append({'code': 'visual', 'message': 'Добавьте реальный снимок интерфейса или проверенную схему там, где она помогает пройти шаги.'})
        metadata = '\n'.join([pack.get('title',''),pack.get('description','')] + [str(v.get('alt',''))+' '+str(v.get('caption','')) for v in pack.get('visuals',[])])
        if facts:
            linked(metadata, list(facts))
            linked(' '.join(brief.get('limitations',[])), list(facts))
        text = '\n'.join([str(brief.get('limitations',[])),str(brief.get('scope',{})),str(pack.get('author',{})),str([s.get('heading','') for s in sections]),pack.get('title',''),pack.get('description',''),pack.get('summary',''),pack.get('cta','')] + [str(x.get('text','')) for x in sections] + [str(v.get('alt',''))+' '+str(v.get('caption','')) for v in pack.get('visuals',[])])
        for phrase in CLICHES:
            if phrase in text.casefold():
                fail('slop', 'Пустое клише: ' + phrase)
        if UNIVERSAL.search(text):
            fail('universal', 'Универсальное обещание совместимости запрещено; укажите конкретные условия')
        if UNSAFE.search(text):
            fail('unsafe', 'Нельзя советовать отключение защиты системы или нелицензионную активацию')
        if re.search(r'(?:гарантир\w*|обязательн\w*).{0,90}(?:индексац|все\w* нейросет|цитирован)', text, re.I):
            fail('ai_promise', 'Нельзя гарантировать индексацию или цитирование нейросетями')
        if re.search(r'Innovate Serial Protocol\s*[12]', text, re.I):
            conflicts = knowledge(root, 'conflicts.json')
            if any(c['id'] == 'innovate-version' and c['status'] == 'open' for c in conflicts):
                fail('conflict', 'В документации расходятся версии Innovate; сначала закройте конфликт с доказательством')
        if re.search(r'<script\b|\bTODO\b|\bTBD\b|ЗАПОЛНИТЬ|sk-[a-zA-Z0-9]{20,}|Bearer\s+\S{15,}', text, re.I):
            fail('unsafe_text', 'В тексте шаблон, сценарий или похожая на секрет строка')
        dangerous = bool(re.search(r'прошить|записать.{0,20}прошивк|распиновк|пин программирован|адаптаци.{0,20}DSG|отключени.{0,20}(?:ABS|ESP|иммобилайзер)', text, re.I))
        if dangerous and brief.get('risk') != 'high':
            fail('risk_downgrade', 'Операция требует высокого уровня риска и технической приёмки')
        if dangerous or brief.get('risk') == 'high' or brief.get('solution_status') == 'tested':
            review = load(job / 'technical-review.json')
            if review.get('content_hash') != snapshot(root, name) or review.get('mode') != 'human' or not review.get('reviewer') or review.get('approved') is not True:
                fail('technical_review', 'Нужна актуальная проверка инженером для опасной операции или собственного испытания')
    except (MadError, KeyError, TypeError, ValueError, AttributeError, OSError) as exc:
        fail('invalid', str(exc) if isinstance(exc, MadError) else 'Неполная структура или отсутствующий файл')
    from .market import validate_job
    errors.extend(validate_job(root, name))
    return {'ok': not errors, 'errors': errors, 'warnings': warnings,
            'note': 'Это проверка структуры и ограниченных эвристик, не доказательство истинности и не определитель авторства ИИ.'}


def review_template(root, name):
    report = validate(root, name)
    if not report['ok']:
        raise MadError('Сначала устраните ошибки validate')
    path = jobdir(root, name) / 'review.json'
    if path.exists():
        raise MadError('Рецензия уже есть; обновите её после проверки новой версии')
    data = {'content_hash': snapshot(root, name), 'mode': 'human', 'reviewer': '', 'notes': '',
            'checks': {k: False for k in CHECKS}, 'warnings_acknowledged': False}
    save(path, data)
    return data


def approve(root, name, token):
    report = validate(root, name)
    digest = snapshot(root, name)
    if not report['ok'] or token != name + '@' + digest:
        raise MadError('Ошибки проверки или устаревший токен версии')
    job = jobdir(root, name)
    r = load(job / 'review.json')
    if r.get('content_hash') != digest or r.get('mode') != 'human' or not r.get('reviewer') or not r.get('notes') or any(r.get('checks',{}).get(k) is not True for k in CHECKS):
        raise MadError('Нужна заполненная человеком рецензия на эту версию')
    if report['warnings'] and r.get('warnings_acknowledged') is not True:
        raise MadError('Рассмотрите предупреждения')
    data = {'content_hash': digest, 'review_hash': sha(job/'review.json'), 'approved_at': utcnow()}
    technical = job / 'technical-review.json'
    if technical.exists():
        data['technical_review_hash'] = sha(technical)
    save(job / 'approval.json', data)
    return data


def require_approval(root, name):
    if not validate(root, name)['ok']:
        raise MadError('Материал не прошёл проверку')
    job = jobdir(root, name)
    approval = load(job / 'approval.json')
    if approval.get('content_hash') != snapshot(root, name) or approval.get('review_hash') != sha(job/'review.json'):
        raise MadError('Утверждение отсутствует или устарело')
    technical = job / 'technical-review.json'
    if (technical.exists() or approval.get('technical_review_hash')) and (not technical.exists() or approval.get('technical_review_hash') != sha(technical)):
        raise MadError('Техническая рецензия изменилась')
    return approval
