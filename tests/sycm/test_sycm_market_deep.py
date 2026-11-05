import unittest
import tempfile,json
from pathlib import Path
from types import SimpleNamespace
from tb.platforms.sycm import market_deep as m

class MarketDeepTests(unittest.TestCase):
 def args(self,**kw):
  d=dict(report='config-shops',date=None,date_type='day',category=None,page=1,limit=10,seller_type=None,ind_type=None,keyword='',prop_ids='',rank=None,cycle=None,sex='',sex_ratio='',age='',age_ratio='');d.update(kw);return SimpleNamespace(**d)
 def test_config_is_snapshot_read_only(self):
  path,p=m.build_request(self.args());self.assertTrue(path.endswith('getMonitoredListPage.json'));self.assertNotIn('dateRange',p)
  for kw in [dict(date='2026-11-03'),dict(category='16'),dict(keyword='x'),dict(report='delete'),dict(page=0),dict(limit=101),dict(seller_type=1)]:
   with self.assertRaises(ValueError):m.build_request(self.args(**kw))
 def test_category_downstream_uses_official_leaf_and_cateids(self):
  _,p=m.build_request(self.args(report='mining-leaf',date='2026-11-03',category='162104'));self.assertEqual(p['cateIds'],'162104')
  _,p=m.build_request(self.args(report='mining-keywords',date='2026-11-03',category='162104'));self.assertEqual(p['indType'],'supply_demand_rate')
  with self.assertRaises(ValueError):m.build_request(self.args(report='mining-items',date='2026-11-03',category='16'))
 def test_property_and_crowd_bound_to_category(self):
  _,p=m.build_request(self.args(report='prop-detail',date='2026-11-03',category='162104',prop_ids='20608',sex='2',sex_ratio='0.5'));self.assertEqual(p['propIds'],'20608');self.assertEqual(p['sex'],'2')
  with self.assertRaises(ValueError):m.build_request(self.args(report='prop-detail',date='2026-11-03',category='162104',prop_ids='unknown'))
 def test_search_filters_do_not_silently_ignore(self):
  _,p=m.build_request(self.args(report='search-related',date='2026-11-03',keyword='衬衫',rank='bluesea',cycle='yearSync'));self.assertEqual(p['orderBy'],'simWeight');self.assertEqual(p['cycleFlag'],'yearSync')
  for kw in [dict(category='16'),dict(rank='save'),dict(cycle='unknown'),dict(seller_type=1),dict(keyword='')]:
   with self.assertRaises(ValueError):m.build_request(self.args(report='search-related',date='2026-11-03',keyword='衬衫',**{k:v for k,v in kw.items() if k!='keyword'}) if 'keyword' not in kw else self.args(report='search-related',date='2026-11-03'))
 def test_structured_rows_preserve_raw_and_snapshot_scope(self):
  raw={'code':0,'data':{'162104':[{'statDate':{'value':'2026-11-03'},'item':{'itemId':1}}]}}
  r=m.summary(raw,'mining-items','2026-11-03');self.assertEqual(r['row_count'],1);self.assertTrue(r['date_verified']);self.assertIn('162104',raw['data'])
  r=m.summary({'code':0,'data':{'data':[{'name':'A'}],'recordCount':117}},'config-shops',None);self.assertEqual(r['data_status'],'configuration_only');self.assertFalse(r['complete'])
 def test_rival_object_requires_matching_mcp_evidence(self):
  with tempfile.TemporaryDirectory() as t:
   path=Path(t)/'options.json';path.write_text(json.dumps({'source':'shopdate_symc_MCP_extension','report':'rival-shop-options','request':{'path':m.REPORTS['rival-shop-options'][1]},'raw':{'code':0,'data':[{'userId':'ENCRYPTED-ID'}]}}),encoding='utf-8')
   _,p=m.build_request(self.args(report='rival-shop-core',date='2026-11-03',rival_id='ENCRYPTED-ID',evidence_file=str(path)));self.assertEqual(p['rivalUser1Id'],'ENCRYPTED-ID');self.assertEqual(p['marketVersion'],'free')
   with self.assertRaises(ValueError):m.build_request(self.args(report='rival-shop-core',date='2026-11-03',rival_id='arbitrary',evidence_file=str(path)))
  with self.assertRaises(ValueError):m.build_request(self.args(report='rival-shop-core',date='2026-11-03',rival_id='123'))
 def test_native_rival_metric_groups_are_not_missing_payload(self):
  s=m.summary({'code':0,'data':{'rivalShop1':{'uv':{'value':'1万~2万'}},'selfShop':{'uv':{'value':10}}}},'rival-shop-core','2026-11-03');self.assertEqual(s['data_status'],'ok');self.assertEqual(s['row_count'],2)
 def test_native_item_child_does_not_accept_unsupported_crowd(self):
  with self.assertRaises(ValueError):m.build_request(self.args(report='mining-items',date='2026-11-03',category='162104',sex='2',sex_ratio='0.5'))
 def test_detail_pagination_survives_reused_nonpaged_filter_validation(self):
  for report,props in [('price-detail',''),('prop-detail','20608')]:
   _,p=m.build_request(self.args(report=report,date='2026-11-03',category='162104',prop_ids=props,page=2,limit=20));self.assertEqual(p['page'],2);self.assertEqual(p['pageSize'],20)
 def test_native_trends_preserve_error_and_security_classification(self):
  for report in ('rival-shop-trend','rival-item-trend','search-trend'):
   for raw,status in [({'code':1000,'data':{}},'error'),({'code':0,'ret':['FAIL_SYS_USER_VALIDATE'],'data':{}},'security_verification'),({'code':0},'missing_payload')]:
    self.assertEqual(m.summary(raw,report,'2026-11-03')['data_status'],status)

if __name__=='__main__':unittest.main()
