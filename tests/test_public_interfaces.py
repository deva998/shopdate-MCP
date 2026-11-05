"""Offline public-interface and publishing boundaries; synthetic data only."""
import importlib
import importlib.util
import json
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
LOCAL_HOME='/home/'+'alice/private'


def load_file(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def jd(name):
    path=str(ROOT/'components/jd')
    if path not in sys.path:sys.path.insert(0,path)
    return importlib.import_module('tb.platforms.jd.'+name)


class PublicInterfaceTests(unittest.TestCase):
    def test_sycm_workflow_catalog_exposes_partial_market_queries(self):
        module=load_file('public_workflow_catalog',ROOT/'components/jd/shopdate_workflows/catalog.py')
        row=next(x for x in module.catalog('symc')['modules'] if x['id']=='industry')
        self.assertEqual(row['implementation'],'partial_registered_native_queries')
        self.assertTrue({'market-query','market-deep','market-lane'} <= set(row['commands']))
        self.assertNotEqual(row['verification'],'blocked_by_browser_site_policy')

    def audit_text(self,text):
        module=load_file('publication_audit',ROOT/'scripts/verify_release.py')
        with tempfile.TemporaryDirectory() as td:
            (Path(td)/'sample.py').write_text(text,encoding='utf-8')
            return module.audit(Path(td))

    def test_https_route_is_not_a_local_home_directory(self):
        self.assertEqual(self.audit_text('URL="https://example.org/home/bi/pivot/query/data_widget"'),[])

    def test_real_paths_are_rejected_even_beside_public_url(self):
        text='URL="https://example.org/home/bi/pivot/query/data_widget"\npath="'+LOCAL_HOME+'"'
        self.assertTrue(any(x['rule']=='personal_path' for x in self.audit_text(text)))
        self.assertTrue(self.audit_text('path="C:/'+'Users/alice/private"'))

    def test_url_query_and_embedded_windows_paths_still_rejected(self):
        self.assertTrue(self.audit_text('URL="https://example.org/read?file='+LOCAL_HOME+'"'))
        self.assertTrue(self.audit_text('URL="https://example.org/C:/'+'Users/alice/private"'))

    def test_weekly_guide_is_parseable_and_keeps_partial_status(self):
        result=jd('analysis_guide').guide('原生自然周')
        self.assertEqual(len(result['modules']),1)
        self.assertEqual(result['modules'][0]['status'],'partial')
        self.assertIn('周UV',result['content'])

    def test_native_week_overview_and_existing_daily_requests(self):
        module=jd('overview');template={'channel':'all','dateType':'day','interval':'DAY','compareType':'hb'}
        day=module.make_request(template,'2026-10-26')
        self.assertEqual((day['startDate'],day['endDate']),('2026-10-26','2026-10-26'))
        week=module.make_request(template,'2026-10-26',period='week',compare='tb')
        self.assertEqual((week['endDate'],week['compareStartDate'],week['compareEndDate'],week['dateType']),('2026-11-01','2025-10-27','2025-11-02','week'))
        with self.assertRaises(ValueError):module.make_request(template,'2026-10-27',period='week')

    def test_industry_week_uses_official_options_and_omits_unavailable_metric(self):
        module=jd('industry')
        options={'header':{'code':0},'body':{'data':[
            {'dimCode':'saleOrdCate','dimVals':[{'label':'示例类目','value':'123'}]},
            {'dimCode':'popBusiness','dimVals':[{'label':'POP','value':'pop'}]},
            {'dimCode':'channel','dimVals':[{'label':'全部','value':'all'}]},
            {'dimCode':'time','dimVals':[{'code':'week','min':'2024-01-01','max':'2026-11-01','compares':['hb','tb']}]}]}}
        for kind in ('shops','products'):
            body,scope=module.build_request(options,kind,'2026-10-26',category='示例类目',period='week')
            self.assertEqual((body['dateType'],body['endDate']),('week','2026-11-01'))
            self.assertNotIn(module.METRICS[5],body['indicators'])
            self.assertEqual(scope['date_scope'],'complete_week')
        with self.assertRaises(ValueError):module.build_request(options,'shops','2026-10-27',category='示例类目',period='week')

    def test_sycm_historical_periods_and_overlap_boundaries(self):
        module=load_file('public_sycm_traffic',ROOT/'components/ali/tb/platforms/sycm/traffic.py')
        for command in module.COMMANDS:
            for start,end,scope in [('2026-11-01',None,'day'),('2026-10-26','2026-11-01','recent7')]:
                _,params,_=module.build_request(command,start,end,today=date(2026,11,3))
                self.assertEqual(params['dateType'],scope)
        with self.assertRaises(ValueError):module.build_request('traffic-overview','2026-11-03',today=date(2026,11,3))
        with self.assertRaises(ValueError):module.build_request('traffic-overview','2026-11-01','2026-11-02',today=date(2026,11,3))
        result=module.summarize('shop-source-tree',{'data':[]})
        self.assertFalse(result['additive'])
        self.assertEqual(result['coverage'],'returned_tree_only')

    def test_sycm_discovery_is_bounded_to_official_static_resources(self):
        module=load_file('public_sycm_discovery',ROOT/'components/ali/tb/platforms/sycm/interface_discovery.py')
        self.assertEqual(module.validate_page('traffic-board'),'https://sycm.taobao.com/flow/monitor/overview')
        self.assertTrue(module.validate_asset('https://g.alicdn.com/dt/ops-flow/example.js'))
        for url in ['http://g.alicdn.com/dt/ops-flow/example.js','https://example.org/script.js','https://g.alicdn.com/dt/ops-flow/example.js?secret=x']:
            with self.assertRaises(ValueError):module.validate_asset(url)

    def test_custom_daily_sources_and_external_adapter_are_not_published(self):
        component=ROOT/'components/jd';extension=component/'extension/unpacked'
        self.assertNotIn('daily-report-source',(component/'tb/platforms/jd/cli.py').read_text(encoding='utf-8'))
        self.assertFalse((component/'tb/platforms/jd/daily_report_sources.py').exists())
        self.assertFalse((extension/'qingmu-reader.js').exists())
        manifest=json.loads((extension/'manifest.json').read_text(encoding='utf-8'))
        self.assertFalse(any('qingmubest' in x for x in manifest['host_permissions']))
        self.assertIn('https://g.alicdn.com/*',manifest['host_permissions'])
        for name in ['background.js','jd-worker.js']:
            self.assertNotIn('qingmu',(extension/name).read_text(encoding='utf-8').lower())
