"""Проверки обязательного предварительного исследования."""
import copy
import contextlib
import io
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from mad import core, market, render
from mad.cli import main
from fixtures_market import prepare_research
from test_mad import fixture, approve_test


class MarketTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();core.init(self.root)
        self.path=prepare_research(self.root)
    def tearDown(self): self.tmp.cleanup()
    def change(self,fn):
        d=core.load(self.path);fn(d);core.save(self.path,d)
    def check(self): return market.check(self.root,'test-research')
    def test_reposts_are_not_independent(self):
        self.change(lambda d:[o.update(independence_key='one-original') for o in d['observations']])
        self.assertFalse(self.check()['ok'])
    def test_evidence_parent_symlink(self):
        real=self.root/'real';real.mkdir();(real/'note.txt').write_text('Test only')
        (self.root/'alias').symlink_to(real,target_is_directory=True)
        with self.assertRaises(core.MadError):
            market.add_evidence(self.root,'test-research','linked',self.root/'alias/note.txt')
    def test_transitive_reprints(self):
        d=core.load(self.path);reg=market.registry(self.root)
        a=d['observations'][0];b=d['observations'][1]
        duplicate=copy.deepcopy(b);duplicate['independence_key']=a['independence_key']
        self.assertEqual(len(market.independent_groups([a,b,duplicate],reg)),1)
    def test_registered_metadata_is_not_live_search(self):
        self.assertTrue(all(s['access_status']=='recheck_required' for s in market.registry(self.root).values()))
    def test_synthetic_trend_rejected(self):
        self.change(lambda d:d['candidates'][0].update(trend_measurement={'baseline':{'source':'synthetic'}}))
        self.assertFalse(self.check()['ok'])
    def test_trend_requires_provenance(self):
        self.change(lambda d:d['candidates'][0].update(trend_measurement={'baseline':{'source':'unverified'}}))
        self.assertFalse(self.check()['ok'])
    def test_valid_report(self): self.assertTrue(self.check()['ok'])
    def test_blank_report_blocked(self):
        market.start(self.root,'blank');self.assertFalse(market.check(self.root,'blank')['ok'])
        with self.assertRaises(core.MadError):market.build_plan(self.root,'blank')
    def test_new_without_research(self):
        with self.assertRaises(core.MadError):core.new(self.root,'bad','x','com-pair')
    def test_new_without_plan(self):
        (self.root/'content/plans/test-research.json').unlink()
        with self.assertRaises(core.MadError):core.new(self.root,'bad','x','com-pair','test-research')
    def test_stale_report(self):
        self.change(lambda d:d.update(checked_at=(market.today()-timedelta(days=8)).isoformat()))
        self.assertFalse(self.check()['ok'])
    def test_future_report(self):
        self.change(lambda d:d.update(checked_at=(market.today()+timedelta(days=1)).isoformat()))
        self.assertFalse(self.check()['ok'])
    def test_old_window(self):
        self.change(lambda d:d.update(period=['2020-01-01','2020-01-30']))
        self.assertFalse(self.check()['ok'])
    def test_missing_platform_attempt(self):
        self.change(lambda d:d.update(coverage=[r for r in d['coverage'] if r['source_id']!='tiktok-patriot']))
        self.assertFalse(self.check()['ok'])
    def test_blocked_socials_are_honest(self):self.assertTrue(self.check()['ok'])
    def test_metadata_is_not_read(self):
        self.change(lambda d:d['observations'][0].update(status='metadata_only'))
        self.assertFalse(self.check()['ok'])
    def test_source_not_checked(self):
        self.change(lambda d:next(r for r in d['coverage'] if r['source_id']=='adact').update(status='blocked'))
        self.assertFalse(self.check()['ok'])
    def test_no_forged_social_profile(self):
        self.assertFalse(market.belongs('https://vk.ru/unrelated',market.registry(self.root)['motorchik']))
        self.assertTrue(market.belongs('https://vk.com/wall-98515032_11843',market.registry(self.root)['motorchik']))
    def test_missing_market_analysis(self):
        self.change(lambda d:d['analysis'].update(alternatives=''))
        self.assertFalse(self.check()['ok'])
    def test_unread_problem_link_not_evidence(self):
        self.change(lambda d:d['candidates'][0].update(observation_ids=[]))
        self.assertFalse(self.check()['ok'])
    def test_only_one_publisher_not_enough(self):
        self.change(lambda d:d.update(observations=d['observations'][:1]))
        self.assertFalse(self.check()['ok'])
    def test_own_brand_not_independent(self):
        regs=core.knowledge(self.root,'community-sources.json')
        for r in regs:
            if r['id'] in ('adact','turbobazar'):r['relationship']='owned'
        core.save(self.root/'knowledge/community-sources.json',regs)
        self.assertFalse(self.check()['ok'])
    def test_russian_priority(self):
        regs=core.knowledge(self.root,'community-sources.json')
        for r in regs:r['region']='unknown'
        core.save(self.root/'knowledge/community-sources.json',regs)
        self.assertFalse(self.check()['ok'])
    def test_wrong_problem_observation(self):
        self.change(lambda d:d['observations'][0].update(problem_id='afr-scale'))
        self.assertFalse(self.check()['ok'])
    def test_missing_solution_check(self):
        self.change(lambda d:d['candidates'][0].update(solution_checks=[]))
        self.assertFalse(self.check()['ok'])
    def test_forum_is_not_solution_documentation(self):
        self.change(lambda d:d['candidates'][0]['solution_checks'][0].update(url='https://turbobazar.ru/threads/34653/'))
        self.assertFalse(self.check()['ok'])
    def test_evidence_tamper(self):
        (self.path.parent/'evidence/obs-0.txt').write_text('Changed')
        self.assertFalse(self.check()['ok'])
    def test_evidence_path_traversal(self):
        self.change(lambda d:d['observations'][0]['evidence'].update(path='../secret'))
        self.assertFalse(self.check()['ok'])
    def test_no_placeholder_analysis(self):
        self.change(lambda d:d['analysis'].update(summary='ЗАПОЛНИТЬ'))
        self.assertFalse(self.check()['ok'])
    def test_privacy_required(self):
        self.change(lambda d:d['observations'][0].update(public_or_redacted=False))
        self.assertFalse(self.check()['ok'])
    def test_no_fake_trend(self):
        self.assertEqual(self.check()['items'][0]['trend']['status'],'not_measured')
    def test_old_post_not_fresh_demand(self):
        self.change(lambda d:[o.update(occurred_at='2014-06-10') for o in d['observations']])
        self.assertEqual(self.check()['items'][0]['demand'],'historical_or_undated_problem')
    def test_unknown_date_not_new(self):
        self.change(lambda d:[o.update(occurred_at=None) for o in d['observations']])
        self.assertEqual(self.check()['items'][0]['demand'],'historical_or_undated_problem')
    def test_empty_research_can_have_no_plan(self):
        self.change(lambda d:d.update(candidates=[],observations=[]))
        result=market.build_plan(self.root,'test-research');self.assertEqual(result['items'],0)
        with self.assertRaises(core.MadError):core.new(self.root,'bad','x','com-pair','test-research')
    def test_changed_plan_blocked(self):
        p=self.root/'content/plans/test-research.json';d=core.load(p);d['items'][0]['title']='Forged';core.save(p,d)
        with self.assertRaises(core.MadError):core.new(self.root,'bad','x','com-pair','test-research')
    def test_changed_report_requires_new_plan(self):
        self.change(lambda d:d['analysis'].update(summary='New analysis'))
        with self.assertRaises(core.MadError):core.new(self.root,'bad','x','com-pair','test-research')
    def test_cli_plan(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['--workspace',str(self.root),'plan-build','test-research']),0)
    def test_registry_integrity(self):
        rows=market.registry(self.root);self.assertEqual(len(rows),17)
        self.assertTrue({'forum','vk','instagram','tiktok'} <= {r['platform'] for r in rows.values()})
    def test_adapters_rule_has_gate(self):
        self.assertIn('research-check',(core.ENGINE/'AGENTS.md').read_text())


class JobGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.job=fixture(self.root)
    def tearDown(self):self.tmp.cleanup()
    def test_old_job_cannot_export(self):
        p=self.job/'brief.json';d=core.load(p);d.pop('market_research');core.save(p,d)
        self.assertFalse(core.validate(self.root,'example')['ok'])
        with self.assertRaises(core.MadError):render.export(self.root,'example')
    def test_report_change_revokes_article(self):
        approve_test(self.root)
        p=market.folder(self.root,'test-research')/'research.json';d=core.load(p);d['analysis']['summary']='Changed';core.save(p,d)
        with self.assertRaises(core.MadError):core.require_approval(self.root,'example')
    def test_relink_requires_review(self):
        approve_test(self.root)
        p=market.folder(self.root,'test-research')/'research.json';d=core.load(p);d['analysis']['summary']='Updated';core.save(p,d)
        market.build_plan(self.root,'test-research');market.link_job(self.root,'example','test-research')
        self.assertTrue(core.validate(self.root,'example')['ok'])
        with self.assertRaises(core.MadError):core.require_approval(self.root,'example')
    def test_stale_research_revokes_article(self):
        approve_test(self.root)
        with patch('mad.market.today',return_value=market.today()+timedelta(days=8)):
            with self.assertRaises(core.MadError):core.require_approval(self.root,'example')

if __name__=='__main__':unittest.main()
