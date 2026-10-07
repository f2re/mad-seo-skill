"""Синтетические данные только для тестов; не рыночное исследование MAD-auto."""
from mad import core, market


def prepare_research(root, run='test-research'):
    market.start(root, run)
    f=market.folder(root,run)/'research.json';d=core.load(f)
    day=market.today().isoformat()
    def note(key,text='Искусственная заметка исключительно для проверки программы.'):
        rel=f'content/research/{run}/evidence/{key}.txt'
        core.write(core.safe(root,rel),text)
        return {'path':rel,'sha256':core.sha(core.safe(root,rel)),'locator':'TEST ONLY'}
    for row in d['coverage']:
        if row['source_id'] in ('adact','turbobazar','motorchik','instagram-adam','tiktok-patriot'):
            row.update(status='read' if row['source_id'] in ('adact','turbobazar') else 'blocked',
                query='TEST ONLY',checked_at=day,note='Синтетическая проверка; сеть не вызывалась.',evidence=note('coverage-'+row['source_id']))
    d['checked_at']=day
    d['analysis']={k:'Синтетический анализ для тестирования. Рыночные выводы не заявлены.' for k in d['analysis']}
    for i,(sid,address) in enumerate((('adact','https://forum.adact.ru/topic/32124-uzam-na-janvare/'),('turbobazar','https://turbobazar.ru/threads/34653/'))):
        d['observations'].append({'id':'obs-'+str(i),'source_id':sid,'url':address,'read_at':day,'occurred_at':day,
            'status':'read','problem_id':'com-pair','problem':'TEST ONLY: нет связи','attempted_solution':'TEST ONLY: проверил COM-пару',
            'outcome':'Результат не известен','outcome_status':'unresolved','independence_key':sid,
            'public_or_redacted':True,'evidence':note('obs-'+str(i))})
    d['candidates']=[{'problem_id':'com-pair','observation_ids':['obs-0','obs-1'],
        'reader_value':'TEST ONLY: объяснение разницы концов COM-пары','priority_reason':'TEST ONLY: документированная возможность',
        'solution_checks':[{'capability_id':'com-bridge','url':'https://mad-auto.ru/doc_wifi_adapters/svjaz_pk_s_ebu_po_wifi/index.html',
            'checked_at':day,'evidence':note('solution')}],'trend_measurement':None}]
    core.save(f,d)
    market.build_plan(root,run)
    return f
