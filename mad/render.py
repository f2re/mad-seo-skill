"""Безопасный HTML и пакет для импорта в CMS. Сетевой публикации нет."""
from __future__ import annotations

import html
import json
import re
import shutil
from datetime import date
from pathlib import Path

from .core import MadError, config, jobdir, load, require_approval, safe, save, snapshot, url, validate, write

CSS = '''body{margin:0;color:#202126;background:#f5f5f6;font:17px/1.7 system-ui,sans-serif}
header.brand{background:#151519;color:#fff;border-top:5px solid #c42032;padding:20px max(20px,calc((100% - 920px)/2))}
main{max-width:920px;margin:32px auto;padding:32px;background:white;border:1px solid #e1e1e5;border-radius:12px}
h1{font-size:clamp(28px,4vw,42px);line-height:1.15;max-width:25ch}h2{line-height:1.3;margin-top:2em}
a{color:#a41425;text-decoration-thickness:1px;text-underline-offset:3px}a:focus-visible{outline:3px solid #a41425}
.summary{border-left:4px solid #c42032;padding:12px 20px;background:#f9f6f6}.meta,figcaption{font-size:14px;color:#535560}
.warning{border:1px solid #b37418;padding:12px}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%}
th,td{border:1px solid #ccc;padding:8px;text-align:left}img{max-width:100%;height:auto}pre{overflow:auto;background:#f2f2f2;padding:16px}
@media(max-width:600px){main{padding:20px;margin:16px 8px}header.brand{padding:15px}body{font-size:16px}}'''


def inline(text):
    parts = re.split(r'(\[[^\]\n]+\]\(https://[^\s)]+\))', str(text))
    rendered = []
    for part in parts:
        match = re.fullmatch(r'\[([^\]]+)\]\(([^)]+)\)', part)
        if match:
            address = url(match.group(2))
            rendered.append('<a href="' + html.escape(address, quote=True) + '">' + html.escape(match.group(1)) + '</a>')
        else:
            rendered.append(html.escape(part))
    return ''.join(rendered)


def markdown(text):
    """Явное подмножество Markdown; сырой HTML никогда не исполняется."""
    result = []
    for block in re.split(r'\n\s*\n', text.strip()):
        lines = block.splitlines()
        if not lines:
            continue
        if block.startswith('```') and block.endswith('```'):
            result.append('<pre><code>' + html.escape('\n'.join(lines[1:-1])) + '</code></pre>')
        elif len(lines) > 1 and '|' in lines[0] and re.fullmatch(r'[ |:\-]+', lines[1]):
            rows = [[cell.strip() for cell in line.strip('|').split('|')] for line in [lines[0], *lines[2:]]]
            result.append('<div class="table-wrap"><table><thead><tr>' + ''.join('<th scope="col">'+inline(c)+'</th>' for c in rows[0]) + '</tr></thead><tbody>' + ''.join('<tr>'+''.join('<td>'+inline(c)+'</td>' for c in row)+'</tr>' for row in rows[1:]) + '</tbody></table></div>')
        elif all(re.match(r'^\d+\. ', line) for line in lines):
            result.append('<ol>' + ''.join('<li>'+inline(re.sub(r'^\d+\. ', '', line))+'</li>' for line in lines) + '</ol>')
        elif all(line.startswith('- ') for line in lines):
            result.append('<ul>' + ''.join('<li>'+inline(line[2:])+'</li>' for line in lines) + '</ul>')
        else:
            result.append('<p>' + inline(block).replace('\n','<br>') + '</p>')
    return '\n'.join(result)


def export(root, name, approved=False):
    report = validate(root, name)
    if not report['ok']:
        raise MadError('Экспорт заблокирован: исправьте validate')
    if approved:
        require_approval(root, name)
    job = jobdir(root, name)
    brief, pack, sources = [load(job / f) for f in ('brief.json','pack.json','sources.json')]
    author = pack.get('author', {})
    if approved and (not author.get('name') or not author.get('url')):
        raise MadError('Для пакета CMS укажите реального автора или редакцию и публичную страницу автора')
    if author.get('url'):
        url(author['url'])
    for key in ('date_published', 'date_modified'):
        if pack.get(key):
            day = date.fromisoformat(pack[key])
            if day > date.today():
                raise MadError('Дата публикации/изменения ещё не наступила')
    if pack.get('date_published') and pack.get('date_modified') and pack['date_modified'] < pack['date_published']:
        raise MadError('Изменение не может предшествовать публикации')
    dest = safe(root, 'exports/' + name + ('/approved' if approved else '/draft'))
    if dest.exists() and not (dest/'manifest.json').exists() and any(dest.iterdir()):
        raise MadError('Папка экспорта содержит чужие файлы')
    dest.mkdir(parents=True, exist_ok=True)
    canonical = brief['seo']['target_url']
    esc = html.escape
    chunks = ['<p class="summary">' + inline(pack['summary']) + '</p>']
    if brief['scope_mode'] == 'general':
        chunks.append('<p class="warning">Материал опирается на документацию. Точная связка версий вашего оборудования здесь не подтверждена; проверьте её отдельно.</p>')
    else:
        chunks.append('<h2>Проверенная конфигурация</h2><ul>' + ''.join('<li>'+esc(k)+': '+esc(str(v))+'</li>' for k,v in brief['scope'].items())+'</ul>')
    chunks.append('<nav aria-label="Содержание"><ol>' + ''.join('<li><a href="#section-'+str(i)+'">'+esc(s['heading'])+'</a></li>' for i,s in enumerate(pack['sections'],1))+'</ol></nav>')
    facts = {c['id']: c for c in load(job/'claims.json')}
    source_map = {s['id']: s for s in sources}
    for i, section in enumerate(pack['sections'],1):
        referenced = sorted({sid for cid in section['claim_ids'] for sid in facts[cid]['source_ids']})
        references = '<p class="meta">Основание: ' + '; '.join('<a href="'+esc(source_map[sid]['url'],quote=True)+'">'+esc(source_map[sid]['title'])+'</a>' for sid in referenced) + '</p>'
        chunks.append('<section id="section-'+str(i)+'"><h2>'+esc(section['heading'])+'</h2>'+markdown(section['text'])+references+'</section>')
    chunks.append('<aside><h2>Границы решения</h2><ul>' + ''.join('<li>'+inline(x)+'</li>' for x in brief['limitations'])+'</ul></aside>')
    media = []
    for i, visual in enumerate(pack['visuals'],1):
        original = safe(root, visual['path'])
        relative = 'media/' + visual['sha256'] + original.suffix.lower()
        target = safe(dest, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        media.append({'file': relative, 'sha256': visual['sha256'], 'alt': visual['alt'], 'caption': visual['caption']})
        chunks.append('<figure><img loading="lazy" src="'+esc(relative,quote=True)+'" alt="'+esc(visual['alt'],quote=True)+'"><figcaption>'+esc(visual['caption'])+'</figcaption></figure>')
    chunks.append('<h2>Источники и дата проверки</h2><ul>'+''.join('<li><a href="'+esc(s['url'],quote=True)+'">'+esc(s['title'])+'</a> — '+esc(s['locator'])+'; проверено '+esc(s['verified_at'])+'</li>' for s in sources)+'</ul>')
    chunks.append('<p>'+inline(pack['cta'])+'</p>')
    content = '\n'.join(chunks)
    meta = '<p class="meta">'+esc(author.get('name') or 'Автор ещё не указан')
    if pack.get('date_published'):
        meta += ' · Опубликовано <time datetime="'+pack['date_published']+'">'+pack['date_published']+'</time>'
    if pack.get('date_modified'):
        meta += ' · Обновлено <time datetime="'+pack['date_modified']+'">'+pack['date_modified']+'</time>'
    meta += '</p>'
    structured = [{'@context':'https://schema.org','@type':'TechArticle','headline':pack['title'],
        'description':pack['description'],'inLanguage':'ru','mainEntityOfPage':canonical,
        'publisher':{'@type':'Organization','name':config(root)['brand']},
        'citation':[s['url'] for s in sources]},
        {'@context':'https://schema.org','@type':'BreadcrumbList','itemListElement':[
            {'@type':'ListItem','position':1,'name':'Статьи','item':config(root)['site_url'].rstrip('/')+'/blog'},
            {'@type':'ListItem','position':2,'name':pack['title'],'item':canonical}]}]
    if author.get('name') and author.get('url'):
        structured[0]['author'] = {'@type':author.get('type','Person'),'name':author['name'],'url':author['url']}
    if pack.get('date_published'):
        structured[0]['datePublished'] = pack['date_published']
    if pack.get('date_modified'):
        structured[0]['dateModified'] = pack['date_modified']
    encoded = json.dumps(structured, ensure_ascii=False).replace('<','\\u003c')
    # Every local preview remains noindex, including an approved package. The CMS
    # sets indexability and actual publication dates only during its own deployment.
    document = '<!doctype html>\n<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>'+esc(pack['title'])+'</title><meta name="description" content="'+esc(pack['description'],quote=True)+'"><link rel="canonical" href="'+esc(canonical,quote=True)+'"><style>'+CSS+'</style><script type="application/ld+json">'+encoded+'</script></head><body><header class="brand">MAD-auto · ПРЕДПРОСМОТР</header><main><article><h1>'+esc(pack['title'])+'</h1>'+meta+content+'</article></main></body></html>'
    write(dest/'preview.html', document)
    write(dest/'article.html', '<article><h1>'+esc(pack['title'])+'</h1>'+meta+content+'</article>')
    write(dest/'article.md', '# '+pack['title']+'\n\n'+pack['summary']+'\n\n'+'\n\n'.join('## '+s['heading']+'\n\n'+s['text'] for s in pack['sections']))
    save(dest/'structured-data.json',structured)
    save(dest/'cms-payload.json',{'schema_version':1,'status':'approved_for_import' if approved else 'draft',
        'slug':name,'title':pack['title'],'description':pack['description'],'canonical':canonical,
        'action':brief['seo']['action'],'existing_urls':brief['seo']['existing_urls'],
        'body_file':'article.html','media':media,'author':author,
        'date_published':pack.get('date_published'),'date_modified':pack.get('date_modified'),
        'deployment_requirements':['Назначить реальные URL медиа и заменить локальные пути',
            'Установить настоящую дату публикации в видимый текст и JSON-LD',
            'Проверить canonical, HTTP 200, robots, noindex, sitemap и серверный HTML',
            'Не копировать noindex из preview.html на опубликованную статью']})
    save(dest/'manifest.json',{'slug':name,'content_hash':snapshot(root,name),'approved':approved,
        'published':False,'files':['article.html','article.md','preview.html','cms-payload.json','structured-data.json']})
    return {'path':str(dest),'approved':approved,'published':False,'network_called':False}
