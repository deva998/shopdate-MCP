import unittest
from types import SimpleNamespace
from tb.platforms.sycm import market_queries as m

class MarketQueriesTests(unittest.TestCase):
 def args(self,**kw):
  d=dict(report='shops',category='16',date='2026-11-03',page=1,limit=10,seller_type=None,rank=None,price_seg='all',min_price=None,max_price=None,keyword='');d.update(kw);return SimpleNamespace(**d)
 def test_native_version_category_and_price_contract(self):
  path,p=m.build_request(self.args(),today='2026-11-04')
  self.assertEqual(path,'/mc/mq/mkt/shop/offline/rank.json');self.assertEqual(p['marketVersion'],'free');self.assertEqual(p['cateId'],'16');self.assertEqual(p['priceSeg'],'')
  _,p=m.build_request(self.args(price_seg='3',page=2),today='2026-11-04');self.assertEqual(p['priceSeg'],'3');self.assertEqual(p['page'],2)
 def test_reject_invalid_or_unverified_filters(self):
  for kw in [dict(category='9999991104'),dict(category='not-a-category'),dict(price_seg='99'),dict(page=0),dict(limit=101),dict(date='2026-11-04'),dict(rank='save'),dict(min_price='100',max_price='50'),dict(min_price='NaN',max_price='100'),dict(keyword='x',report='categories')]:
   with self.assertRaises(ValueError,msg=str(kw)):m.build_request(self.args(**kw),today='2026-11-04')
 def test_leaf_required_and_options_are_not_statistics(self):
  with self.assertRaises(ValueError):m.build_request(self.args(report='insight-price'),today='2026-11-04')
  _,p=m.build_request(self.args(report='insight-price',category='162104'),today='2026-11-04');self.assertEqual(p['indType'],'pay_ord_amt')
  self.assertEqual(m.summarize_market({'code':0},kind='statistics')['data_status'],'missing_payload')
  self.assertEqual(m.summarize_market({'code':0,'data':{'HgLp':[],'HgHp':[],'LgHp':[]}},kind='statistics')['data_status'],'no_data')
  self.assertEqual(m.summarize_market({'code':0,'data':[{'name':'风格','id':20608}]},kind='options')['data_status'],'options_only')
 def test_group_statistics_preserve_interval_strings_and_dates(self):
  r=m.summarize_market({'code':0,'data':{'HgHp':[{'statDate':{'value':'2026-11-03'},'payByrCnt':{'value':'7.5万 ~ 10万'}}]}},kind='statistics',day='2026-11-03')
  self.assertEqual(r['data_status'],'ok');self.assertEqual(r['row_count'],1);self.assertTrue(r['date_verified']);self.assertFalse(r['complete'])
  self.assertEqual(m.summarize_market({'code':0,'data':{'HgHp':[{'statDate':{'value':'2026-11-02'}}]}},kind='statistics',day='2026-11-03')['data_status'],'date_mismatch')
 def test_snapshot_cannot_claim_historical_date(self):
  with self.assertRaises(ValueError):m.build_request(self.args(report='categories'),today='2026-11-04')
  path,p=m.build_request(self.args(report='categories',category=None,date=None),today='2026-11-04');self.assertEqual(p,{'marketVersion':'free'})
 def test_native_property_selection_and_safety_response(self):
  _,p=m.build_request(self.args(report='insight-prop',category='162104',prop_ids='20608'),today='2026-11-04');self.assertEqual(p['propIds'],'20608')
  with self.assertRaises(ValueError):m.build_request(self.args(report='insight-prop',category='162104',prop_ids='99999'),today='2026-11-04')
  raw={'ret':['FAIL_SYS_USER_VALIDATE'],'data':{'url':'https://sycm.taobao.com/punish?x5secdata=SECRET'}}
  self.assertEqual(m.summarize_market(raw,kind='statistics')['data_status'],'security_verification')
  self.assertNotIn('SECRET',str(m.redact_verification(raw)))
 def test_official_statdate_epoch_uses_china_timezone(self):
  r=m.summarize_market({'code':0,'data':{'data':[{'statDate':{'value':1793635200000}}]}},kind='statistics',day='2026-11-03');self.assertTrue(r['date_verified'])
 def test_stale_ai_sample_cannot_masquerade_as_yesterday(self):
  with self.assertRaises(ValueError):m.build_request(self.args(report='ai-styles'),today='2026-11-04')
  _,p=m.build_request(self.args(report='ai-styles',date='2026-02-08'),today='2026-11-04');self.assertEqual(p['dateRange'],'2026-02-08|2026-02-08')
  with self.assertRaises(ValueError):m.build_request(self.args(report='ai-styles',date='2026-02-08',prop_ids='20608'),today='2026-11-04')
 def test_explicit_seller_type_cannot_be_silently_ignored(self):
  for report,cat,day in [('search','16','2026-11-03'),('price-options','16','2026-11-03'),('insight-attributes','162104','2026-11-03'),('ai-styles','16','2026-02-08')]:
   with self.assertRaises(ValueError,msg=report):m.build_request(self.args(report=report,category=cat,date=day,seller_type=1),today='2026-11-04')
  _,p=m.build_request(self.args(seller_type=1),today='2026-11-04');self.assertEqual(p['sellerType'],1)
 def test_native_extra_item_ranks_and_periods(self):
  for rank,suffix in [('growth','rank.json'),('newitm_ipv','rank.json'),('recommend_flow','rank/recommend.json'),('growth_flow','rank/rise.json')]:
   path,p=m.build_request(self.args(report='items',rank=rank),today='2026-11-05');self.assertTrue(path.endswith(suffix));self.assertEqual(p['rankType'],rank)
  _,p=m.build_request(self.args(date='2026-11-01',date_type='week'),today='2026-11-05');self.assertEqual(p['dateRange'],'2026-10-26|2026-11-01');self.assertEqual(p['dateType'],'week')
  _,p=m.build_request(self.args(date='2026-10-31',date_type='month'),today='2026-11-05');self.assertEqual(p['dateRange'],'2026-10-01|2026-10-31')
  _,p=m.build_request(self.args(rank='growth'),today='2026-11-05');self.assertEqual(p['rankType'],'growth')
  with self.assertRaises(ValueError):m.build_request(self.args(rank='flow'),today='2026-11-05')
  for kw in [dict(date_type='custom'),dict(date_type='week',date='2026-11-03'),dict(date_type='month',date='2026-11-03'),dict(report='ai-styles',date='2026-02-08',date_type='week')]:
   with self.assertRaises(ValueError):m.build_request(self.args(**kw),today='2026-11-05')
 def test_official_crowd_pairs_and_metric_restrictions(self):
  _,p=m.build_request(self.args(report='insight-price',category='162104',ind_type='pay_ord_cnt',sex='2',sex_ratio='0.5',age='2',age_ratio='0.2'),today='2026-11-05');self.assertEqual(p['indType'],'pay_ord_cnt');self.assertEqual(p['sexRatio'],'0.5')
  for kw in [dict(report='shops',sex='2',sex_ratio='0.5'),dict(report='insight-price',category='162104',sex='2'),dict(report='insight-price',category='162104',age='7',age_ratio='0.5'),dict(report='insight-price',category='162104',ind_type='supply_demand_rate')]:
   with self.assertRaises(ValueError):m.build_request(self.args(**kw),today='2026-11-05')

if __name__=='__main__':unittest.main()
