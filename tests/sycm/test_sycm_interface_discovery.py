import importlib.util
from pathlib import Path
import unittest

SOURCE=Path(__file__).resolve().parents[2]/'components/ali/tb/platforms/sycm/interface_discovery.py'
spec=importlib.util.spec_from_file_location('discovery',SOURCE)
d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)

class DiscoveryTests(unittest.TestCase):
 def test_extensionless_fashion_lane_queries_are_discovered(self):
  result=d.parse_source('"/s_portal/fashion/trend/categories";"/s_portal/fashion/trend/filters";"/s_portal/fashion/trend/rankings";"/s_portal/fashion/trend/seller-items";"/s_portal/fashion/trend/save"','https://g.alicdn.com/dt/op-market/1.0.135/70.js')
  self.assertEqual(result['candidate_paths'],['/s_portal/fashion/trend/categories','/s_portal/fashion/trend/filters','/s_portal/fashion/trend/rankings','/s_portal/fashion/trend/seller-items'])
 def test_quickbi_hashed_chunk_loader(self):
  source='o.src=function(d){return f.p+""+({}[d]||d)+"."+{449:"f01e"}[d]+".chunk.js"}(d)'
  parsed=d.parse_source(source,'https://g.alicdn.com/qbi/qbi/4.3.167/dashboardview.js')
  self.assertIn('https://g.alicdn.com/qbi/qbi/4.3.167/449.f01e.chunk.js',parsed['chunk_asset_references'])
 def test_observed_quickbi_static_project(self):
  url='https://g.alicdn.com/qbi/qbi/4.3.167/entry-loader.js'
  self.assertEqual(d.validate_asset(url),url)
  self.assertEqual(d.validate_asset(url.replace('entry-loader.js','vendors~dashboard.1234.chunk.js')),url.replace('entry-loader.js','vendors~dashboard.1234.chunk.js'))
  with self.assertRaises(ValueError):d.validate_asset('https://g.alicdn.com/qbi/admin/1/admin.js')
 def test_chunk_loader_variable_is_not_hardcoded(self):
  source='c.src=function(e){return i.p+""+({1:"Common"}[e]||e)+".js"}(e);i.p="//g.alicdn.com/dt/op-market/1.0.135/";r.e(74)'
  parsed=d.parse_source(source,'https://g.alicdn.com/dt/op-market/1.0.135/vendors.js')
  self.assertIn('https://g.alicdn.com/dt/op-market/1.0.135/74.js',parsed['chunk_asset_references'])
 def test_market_and_zone_menu_entries_and_source_families(self):
  self.assertEqual(d.validate_page('market-ranking'),'https://sycm.taobao.com/mc/free/market_rank')
  self.assertEqual(d.validate_page('zone-information-flow'),'https://sycm.taobao.com/xsite/shoutao/information-flow.htm')
  for project in ['op-market','oneness-page']:
   self.assertEqual(d.validate_asset(f'https://g.alicdn.com/dt/{project}/1.0.1/app.js'),f'https://g.alicdn.com/dt/{project}/1.0.1/app.js')
  parsed=d.parse_source('ctxMarketVersion=1.0.135;ctxOnenessPageVersion=1.5.48;','https://sycm.taobao.com/mc/free/market_rank')
  self.assertIn('https://g.alicdn.com/dt/op-market/1.0.135/app.js',parsed['derived_project_assets'])
  self.assertIn('https://g.alicdn.com/dt/oneness-page/1.5.48/app.js',parsed['derived_project_assets'])
 def test_javascript_regex_is_not_parsed_as_html(self):
  result=d.parse_source('var re=/<![A-Za-z]>/;var url="/cc/refund/list.json";','https://g.alicdn.com/dt/op-cc/2.4.238/app.js')
  self.assertEqual(result['candidate_paths'],['/cc/refund/list.json'])
 def test_registered_pages_only(self):
  self.assertEqual(d.validate_page('customer-overview'),'https://sycm.taobao.com/cc/customer/overview')
  self.assertEqual(d.validate_page('content-overview'),'https://sycm.taobao.com/xsite/contentanalysis/overview_new_v2')
  self.assertEqual(d.validate_page('service-core'),'https://sycm.taobao.com/qos/service/core_monitor/new')
  self.assertEqual(d.validate_page('trade-realtime'),'https://sycm.taobao.com/ipoll/index.htm')
  self.assertTrue(d.validate_page('sales-overview').endswith('/bda/tradinganaly/overview/overview.htm'))
  with self.assertRaises(ValueError):d.validate_page('https://evil.example/')
 def test_no_credentials_or_unregistered_static_sources(self):
  self.assertEqual(d.validate_asset('https://g.alicdn.com/dt/op-cp/4.0.133/app.js'),'https://g.alicdn.com/dt/op-cp/4.0.133/app.js')
  self.assertEqual(d.validate_asset('https://g.alicdn.com/dt/ops-base/1.0.11/js/ops-base.js'),'https://g.alicdn.com/dt/ops-base/1.0.11/js/ops-base.js')
  self.assertEqual(d.validate_asset('https://g.alicdn.com/dt/ops-bda/1.0.15/js/trade/overview/app.js'),'https://g.alicdn.com/dt/ops-bda/1.0.15/js/trade/overview/app.js')
  for url in ['https://g.alicdn.com/dt/ops-bda/1.0.15/js/admin/app.js','https://g.alicdn.com/dt/op-fa/1/app.js?token=x','https://g.alicdn.com/dt/op-fa/../file.js']:
   with self.assertRaises(ValueError):d.validate_asset(url)
 def test_official_version_metadata_and_read_candidates(self):
  result=d.parse_source('ctxFaVersion=1.0.36;ctxLiveVersion=5.0.90;"/ipoll/live/getFlowAndPay.json";"/fa/save.json"','https://sycm.taobao.com/ipoll/index.htm')
  self.assertEqual(result['project_versions']['op-fa'],'1.0.36')
  self.assertIn('https://g.alicdn.com/dt/op-live/5.0.90/app.js',result['derived_project_assets'])
  self.assertEqual(result['candidate_paths'],['/ipoll/live/getFlowAndPay.json'])

if __name__=='__main__':unittest.main()
