"""Искусственные данные. Проверка кода, не доказательство свойств оборудования."""
import contextlib
import copy
import io
import json
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from mad import core, render, research
from mad.cli import lock, main, knowledge_check
from mad.install import install

ROOT=Path(__file__).resolve().parent.parent


def fixture(root):
    core.init(root)
    core.new(root,'example','Проверка COM-моста','com-pair')
    job=core.jobdir(root,'example')
    note=job/'note.txt';note.write_text('Искусственная заметка теста: программы должны использовать разные концы COM-пары.')
    core.source_add(root,'example','bridge','https://mad-auto.ru/doc_wifi_adapters/svjaz_pk_s_ebu_po_wifi/index.html','Документация COM-моста',note,'Настройка COM-моста','official')
    brief=core.load(job/'brief.json')
    brief.update(problem_source_ids=['bridge'],added_value='Порядок локализации ошибки COM-пары',limitations=['Совместимость версии ЭБУ проверяется отдельно.'])
    core.save(job/'brief.json',brief)
    core.save(job/'claims.json',[{'id':'fact','kind':'procedure','text':'Программы используют разные концы виртуальной COM-пары.','status':'verified','source_ids':['bridge'],'checked_by':'TEST ONLY'}])
    pack=core.load(job/'pack.json')
    pack.update(description='Проверка настройки пары виртуальных портов.',summary='Программы используют разные концы COM-пары.',summary_claim_ids=['fact'],author={'name':'TEST ONLY','url':'https://example.org/test-author'},sections=[{'role':role,'heading':role,'text':'Проверьте разные концы виртуальной COM-пары.','claim_ids':['fact']} for role in ('scope','requirements','steps','result','troubleshooting','limitations')])
    core.save(job/'pack.json',pack)
    return job


def approve_test(root):
    core.review_template(root,'example')
    p=core.jobdir(root,'example')/'review.json'
    r=core.load(p);r.update(mode='human',reviewer='TEST ONLY',notes='Синтетическая рецензия для теста',checks={k:True for k in core.CHECKS},warnings_acknowledged=True)
    core.save(p,r)
    core.approve(root,'example','example@'+core.snapshot(root,'example'))


class Workspace(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve();self.job=fixture(self.root)
    def tearDown(self):self.temp.cleanup()
    def change(self,name,mutator):
        data=core.load(self.job/name);mutator(data);core.save(self.job/name,data)
    def codes(self):return {e['code'] for e in core.validate(self.root,'example')['errors']}
    def test_good_fixture(self):self.assertTrue(core.validate(self.root,'example')['ok'])
    def test_init_preserves_config(self):
        p=self.root/'mad.json';c=core.load(p);c['brand']='Custom';core.save(p,c);core.init(self.root);self.assertEqual(core.load(p)['brand'],'Custom')
    def test_duplicate_job(self):
        with self.assertRaises(core.MadError):core.new(self.root,'example','x','com-pair')
    def test_paths(self):
        for value in ('../secret','/tmp/secret','a/../../b','a\\b'):
            with self.subTest(value=value),self.assertRaises(core.MadError):core.safe(self.root,value)
    def test_symlink(self):
        (self.root/'link').symlink_to(self.job)
        with self.assertRaises(core.MadError):core.safe(self.root,'link/pack.json')
    def test_duplicate_json_and_nan(self):
        for text in ('{"a":1,"a":2}','{"a":NaN}'):
            p=self.root/'invalid.json';p.write_text(text)
            with self.assertRaises(core.MadError):core.load(p)
    def test_bad_url(self):
        for value in ('http://example.org','https://user:pass@example.org','javascript:alert(1)','https://example.org?access_token=secret'):
            with self.subTest(value=value),self.assertRaises(core.MadError):core.url(value)
    def test_lock(self):
        with lock(self.root):
            with self.assertRaises(core.MadError):
                with lock(self.root):pass
    def test_source_tamper(self):
        (self.job/'evidence/bridge.txt').write_text('Изменено')
        self.assertIn('source_hash',self.codes())
    def test_future_source(self):
        self.change('sources.json',lambda d:d[0].update(verified_at=(date.today()+timedelta(days=1)).isoformat()))
        self.assertIn('future_source',self.codes())
    def test_stale_source(self):
        self.change('sources.json',lambda d:d[0].update(verified_at=(date.today()-timedelta(days=181)).isoformat()))
        self.assertIn('stale_source',self.codes())
    def test_forum_not_solution(self):
        self.change('sources.json',lambda d:d[0].update(kind='forum'))
        self.assertIn('primary',self.codes());self.assertIn('capability_source',self.codes())
    def test_missing_demand(self):
        self.change('brief.json',lambda d:d.update(problem_source_ids=[]))
        self.assertIn('problem_evidence',self.codes())
    def test_wrong_capability(self):
        self.change('brief.json',lambda d:d.update(capability_ids=['afr-input']))
        self.assertIn('fit',self.codes())
    def test_unregistered_problem(self):
        self.change('brief.json',lambda d:d.update(problem_id='generic-auto-news'))
        self.assertIn('problem',self.codes())
    def test_unknown_versions(self):
        self.change('brief.json',lambda d:d.update(scope_mode='exact'))
        self.assertIn('compatibility',self.codes())
    def test_specific_claim_general_scope(self):
        self.change('claims.json',lambda d:d[0].update(kind='compatibility'))
        self.assertIn('claim_scope',self.codes())
    def test_solution_not_tested_without_review(self):
        self.change('brief.json',lambda d:d.update(solution_status='tested'))
        self.assertFalse(core.validate(self.root,'example')['ok'])
    def test_existing_intent(self):
        self.change('brief.json',lambda d:d.update(problem_id='download-csv',capability_ids=['logger-download']))
        self.assertIn('duplicate',self.codes())
    def test_canonical_host(self):
        self.change('brief.json',lambda d:d['seo'].update(target_url='https://evil.example/blog/example'))
        self.assertIn('canonical',self.codes())
    def test_unlinked_section(self):
        self.change('pack.json',lambda d:d['sections'][0].update(claim_ids=[]))
        self.assertIn('unlinked',self.codes())
    def test_unsupported_number(self):
        self.change('pack.json',lambda d:d['sections'][0].update(text='Подайте 99 В.'))
        self.assertIn('numeric',self.codes())
    def test_metadata_number(self):
        self.change('pack.json',lambda d:d.update(description='Питание 99 В.'))
        self.assertIn('numeric',self.codes())
    def test_slop(self):
        self.change('pack.json',lambda d:d.update(summary='В современном мире это новый уровень диагностики.'))
        self.assertIn('slop',self.codes())
    def test_universal(self):
        self.change('pack.json',lambda d:d['sections'][0].update(text='Подходит всем автомобилям.'))
        self.assertIn('universal',self.codes())
    def test_disable_firewall(self):
        self.change('pack.json',lambda d:d['sections'][0].update(text='Отключите брандмауэр.'))
        self.assertIn('unsafe',self.codes())
    def test_innovate_conflict(self):
        self.change('pack.json',lambda d:d['sections'][0].update(text='Выход Innovate Serial Protocol 1.'))
        self.assertIn('conflict',self.codes())
    def test_risk_downgrade(self):
        self.change('pack.json',lambda d:d['sections'][0].update(text='Записать новую прошивку.'))
        self.assertIn('risk_downgrade',self.codes())
    def test_ai_guarantee(self):
        self.change('pack.json',lambda d:d['sections'][0].update(text='Гарантируем индексацию всеми нейросетями.'))
        self.assertIn('ai_promise',self.codes())
    def test_incomplete_article(self):
        self.change('pack.json',lambda d:d.update(sections=[]))
        self.assertIn('structure',self.codes())
    def test_metadata_secret(self):
        self.change('pack.json',lambda d:d.update(description='Bearer abcdefghijklmnopqrstuvwxyz'))
        self.assertIn('unsafe_text',self.codes())
    def test_draft_export(self):
        result=render.export(self.root,'example');p=Path(result['path'])
        self.assertIn('noindex', (p/'preview.html').read_text());self.assertFalse(result['published']);self.assertFalse(result['network_called'])
        self.assertEqual(core.load(p/'cms-payload.json')['status'],'draft')
    def test_approved_requires_review(self):
        with self.assertRaises(core.MadError):render.export(self.root,'example',True)
    def test_approval_and_revocation(self):
        approve_test(self.root);self.assertIsNotNone(core.require_approval(self.root,'example'))
        self.change('pack.json',lambda d:d.update(cta='Проверьте документацию.'))
        with self.assertRaises(core.MadError):core.require_approval(self.root,'example')
    def test_review_mutation(self):
        approve_test(self.root)
        self.change('review.json',lambda d:d.update(notes='Другая рецензия'))
        with self.assertRaises(core.MadError):core.require_approval(self.root,'example')
    def test_knowledge_mutation(self):
        approve_test(self.root);(self.root/'knowledge').mkdir();core.save(self.root/'knowledge/conflicts.json',core.knowledge(self.root,'conflicts.json'))
        with self.assertRaises(core.MadError):core.require_approval(self.root,'example')
    def test_approved_bundle_stays_local_noindex(self):
        approve_test(self.root);result=render.export(self.root,'example',True);p=Path(result['path'])
        self.assertIn('noindex',(p/'preview.html').read_text());self.assertFalse(result['published'])
        data=core.load(p/'structured-data.json');self.assertNotIn('datePublished',data[0]);self.assertEqual(data[0]['@type'],'TechArticle')
    def test_no_foreign_export_overwrite(self):
        p=self.root/'exports/example/draft';p.mkdir(parents=True);(p/'private.txt').write_text('keep')
        with self.assertRaises(core.MadError):render.export(self.root,'example')
        self.assertEqual((p/'private.txt').read_text(),'keep')
    def test_html_escape(self):
        text=render.markdown('<img onerror="evil">\n\n1. Первый\n2. Второй')
        self.assertNotIn('<img',text);self.assertIn('&lt;img',text);self.assertIn('<ol>',text)
    def test_table_render(self):self.assertIn('<table>',render.markdown('A | B\n---|---\nx | y'))
    def test_cli_unknown(self):
        with contextlib.redirect_stdout(io.StringIO()):self.assertEqual(main(['--workspace',str(self.root),'knowledge-check']),0)
    def test_source_add_duplicate(self):
        with self.assertRaises(core.MadError):core.source_add(self.root,'example','bridge','https://example.org','x',self.job/'note.txt','x','official')


class ResearchTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);core.init(self.root)
    def tearDown(self):self.temp.cleanup()
    def signal(self):
        return {'id':'one','problem_id':'com-pair','url':'https://example.org/thread?utm_source=x','occurred_at':date.today().isoformat(),'observed_at':date.today().isoformat(),'kind':'forum','evidence':'Test issue','attempted_solution':'Test attempt','independence_key':'original-thread','public_or_redacted':True}
    def test_no_fake_trend(self):
        result=research.rank(self.root)
        self.assertTrue(all(x['trend']=='not_measured' and x['status']=='documentation_hypothesis' for x in result['topics']))
    def test_signals_duplicate(self):
        a=self.signal();b=copy.deepcopy(a);b.update(id='two',url='https://example.org/thread?utm_source=y')
        p=self.root/'signals.json';core.save(p,[a,b]);self.assertEqual(research.import_signals(self.root,p)['records'],1)
    def test_unknown_event_not_current(self):
        a=self.signal();a['occurred_at']=None;p=self.root/'signals.json';core.save(p,[a]);research.import_signals(self.root,p)
        result=research.rank(self.root);self.assertTrue(all(x['independent_signals']==0 for x in result['topics']))
    def test_privacy_blocks(self):
        a=self.signal();a['public_or_redacted']=False;p=self.root/'signals.json';core.save(p,[a])
        with self.assertRaises(core.MadError):research.import_signals(self.root,p)
    def test_historical_event_not_current(self):
        a=self.signal();a['occurred_at']=(date.today()-timedelta(days=365)).isoformat();p=self.root/'signals.json';core.save(p,[a]);research.import_signals(self.root,p)
        self.assertTrue(all(x['independent_signals']==0 for x in research.rank(self.root)['topics']))
    def test_search_plan_is_not_results(self):self.assertFalse(research.search_plan(self.root)['search_executed'])
    def trend(self):
        end=date.today()-timedelta(days=1);start=end-timedelta(days=29);previous=start-timedelta(days=30)
        a={'source':'test','unit':'impressions','scope':'same-query','days':30,'complete':True,'value':100,'start':previous.isoformat(),'end':(start-timedelta(days=1)).isoformat()}
        b={**a,'value':130,'start':start.isoformat(),'end':end.isoformat()}
        return {'baseline':a,'current':b}
    def test_trend_comparable(self):self.assertEqual(research.measured_trend(self.trend())['status'],'rising')
    def test_trend_low_base(self):
        d=self.trend();d['baseline']['value']=0;self.assertEqual(research.measured_trend(d)['status'],'insufficient_data')
    def test_trend_incomplete(self):
        d=self.trend();d['current']['complete']=False;self.assertEqual(research.measured_trend(d)['status'],'insufficient_data')
    def test_trend_different_source(self):
        d=self.trend();d['current']['source']='other';self.assertEqual(research.measured_trend(d)['status'],'incomparable')
    def test_trend_overlap(self):
        d=self.trend();d['current']['start']=d['baseline']['start'];d['current']['end']=d['baseline']['end'];self.assertEqual(research.measured_trend(d)['status'],'incomparable')
    def test_trend_nan(self):
        d=self.trend();d['current']['value']=float('nan')
        with self.assertRaises(core.MadError):research.measured_trend(d)
    def test_analytics_missing_and_idempotent(self):
        p=self.root/'metrics.csv';p.write_text('date,page,query,clicks,impressions\n'+date.today().isoformat()+',https://m.wifiobd.ru/blog/test,test,,100\n')
        research.analytics_import(self.root,p,'google');research.analytics_import(self.root,p,'google');row=research.analytics_report(self.root)['pages'][0]
        self.assertIsNone(row['ctr']);self.assertEqual(row['query_rows'],1);self.assertIsNone(row['observed_clicks'])
    def test_analytics_no_data(self):self.assertEqual(research.analytics_report(self.root)['status'],'no_data')
    def test_knowledge_contract(self):self.assertTrue(knowledge_check(self.root)['ok'])


class InstallTests(unittest.TestCase):
    def test_install_idempotent_conflict_and_preservation(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'work';self.assertTrue(install(target,True)['dry_run']);self.assertFalse(target.exists())
            install(target);install(target)
            (target/'AGENTS.md').write_text('CUSTOM')
            with self.assertRaises(core.MadError):install(target)
            self.assertEqual((target/'AGENTS.md').read_text(),'CUSTOM')
    def test_native_adapters_current(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('sync',ROOT/'tools/sync_adapters.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        for rel,text in m.generated().items():
            self.assertEqual((ROOT/rel).read_text(),text)
    def test_no_runtime_network_imports(self):
        # URL parsing is permitted. No transport/LLM client hidden in the article toolkit.
        for p in (ROOT/'mad').glob('*.py'):
            t=p.read_text();self.assertNotIn('urllib.request',t);self.assertNotIn('import requests',t);self.assertNotIn('import openai',t)

if __name__=='__main__':unittest.main()
