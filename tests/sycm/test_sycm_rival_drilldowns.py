import unittest,json,tempfile
from pathlib import Path
from types import SimpleNamespace
from tb.platforms.sycm import market_deep as m

class RivalDrilldownTests(unittest.TestCase):
 def args(self,**kw):
  d=dict(report='rival-shop-profile',date='2026-11-03',date_type='day',category=None,page=1,limit=10,seller_type=None,ind_type=None,keyword='',prop_ids='',rank=None,cycle=None,sex='',sex_ratio='',age='',age_ratio='',rival_id='shop',evidence_file=None,metric=None,audience=None);d.update(kw);return SimpleNamespace(**d)
 def evidence(self,directory,item=False):
  report='monitor-items' if item else 'rival-shop-options';path=Path(directory)/'evidence.json';path.write_text(json.dumps({'source':'shopdate_symc_MCP_extension','report':report,'request':{'path':m.REPORTS[report][1],'params':{'dateType':'day','dateRange':'2026-11-03|2026-11-03'}},'raw':{'code':0,'data':{'data':[{'itemId':{'value':'item'}}]} if item else [{'userId':'shop'}]}}),encoding='utf-8');return str(path)
 def test_shop_audience_and_native_product_id_key(self):
  with tempfile.TemporaryDirectory() as t:
   e=self.evidence(t)
   _,p=m.build_request(self.args(evidence_file=e,audience='payByrCnt'));self.assertEqual(p['topType'],'payByrCnt');self.assertEqual(p['rivalUser1Id'],'shop')
   _,p=m.build_request(self.args(report='rival-shop-products',evidence_file=e,metric='payByrCnt'));self.assertEqual(p['rivalUserId'],'shop');self.assertNotIn('rivalUser1Id',p)
 def test_item_material_sort_and_evidence_binding(self):
  with tempfile.TemporaryDirectory() as t:
   e=self.evidence(t,True)
   _,p=m.build_request(self.args(report='rival-item-material',rival_id='item',evidence_file=e,metric='itemLossRate'));self.assertEqual(p['order'],'asc');self.assertEqual(p['rivalItem1Id'],'item');self.assertNotIn('selfItemId',p)
   for kw in [dict(page=2),dict(metric='save'),dict(audience='uv'),dict(date_type='week',date='2026-11-01'),dict(rival_id='wrong')]:
    args=self.args(report='rival-item-material',rival_id='item',evidence_file=e);vars(args).update(kw)
    with self.assertRaises(ValueError):m.build_request(args)
 def test_keywords_top10_does_not_accept_pagination_or_ignored_filter(self):
  with tempfile.TemporaryDirectory() as t:
   e=self.evidence(t)
   _,p=m.build_request(self.args(report='rival-shop-keywords',evidence_file=e,metric='payRate'));self.assertEqual(p['orderBy'],'payRate');self.assertEqual(p['pageSize'],10)
   with self.assertRaises(ValueError):m.build_request(self.args(report='rival-shop-core',evidence_file=e,metric='payRate'))
 def test_nested_materials_preserve_empty_video_and_nonempty_gallery(self):
  raw={'code':0,'data':{'selfItem':{},'rivalItem1':{'video':[],'gallery':[{'statDate':{'value':'2026-11-03'},'contentInfo':{'value':'image-url'}}]}}}
  s=m.summary(raw,'rival-item-material','2026-11-03');self.assertEqual(s['data_status'],'ok');self.assertEqual(s['row_count'],1);self.assertIn('rivalItem1.video',s['empty_sections']);self.assertTrue(s['date_verified'])
  self.assertEqual(m.summary({'code':0,'data':{'rivalItem1':{'video':[],'gallery':[]}}},'rival-item-material','2026-11-03')['data_status'],'no_data')
 def test_all_metric_trend_axes_use_value_never_draw_and_security_first(self):
  raw={'code':0,'data':{'rivalItem1':{'all':{'statDate':[1793635200000],'itemExposeUv':{'value':['100~200'],'drawValue':[100]}}}}}
  s=m.summary(raw,'rival-item-detail-trend','2026-11-03');self.assertEqual(s['data_status'],'ok');self.assertEqual(s['trend_axes']['rivalItem1.all']['metrics'],['itemExposeUv']);self.assertFalse(s['complete'])
  raw['ret']=['FAIL_SYS_USER_VALIDATE'];self.assertEqual(m.summary(raw,'rival-item-detail-trend','2026-11-03')['data_status'],'security_verification')
  self.assertEqual(m.summary({'code':0,'data':{'rivalItem1':{'statDate':[1793635200000],'ndUv':{'drawValue':[10]}}}},'rival-item-recommend-trend','2026-11-03')['data_status'],'partial')
 def test_matching_empty_trend_is_official_empty_not_invalid_axis(self):
  empty={'statDate':[],'itemExposeUv':{'value':[]}}
  raw={'code':0,'data':{'rivalItem1':{'all':empty}}}
  s=m.summary(raw,'rival-item-detail-trend','2026-11-03');self.assertEqual(s['data_status'],'no_data');self.assertEqual(s['invalid_sections'],[]);self.assertIn('rivalItem1.all',s['empty_sections'])
  raw['data']['rivalItem1']['image']={'statDate':[1793635200000],'itemExposeUv':{'value':['1~2']}}
  self.assertEqual(m.summary(raw,'rival-item-detail-trend','2026-11-03')['data_status'],'ok')
  raw['data']['rivalItem1']['all']={'statDate':[],'itemExposeUv':{'value':[1]}}
  self.assertEqual(m.summary(raw,'rival-item-detail-trend','2026-11-03')['data_status'],'partial')
 def test_native_week_month_preserve_same_period_object_evidence(self):
  with tempfile.TemporaryDirectory() as t:
   e=self.evidence(t,True)
   for period,end,start in [('week','2026-11-01','2026-10-26'),('month','2026-10-31','2026-10-01')]:
    evidence=json.loads(Path(e).read_text(encoding='utf-8'));evidence['request']['params'].update(dateType=period,dateRange=start+'|'+end);Path(e).write_text(json.dumps(evidence),encoding='utf-8')
    for report in ['rival-item-keywords','rival-item-detail-core','rival-item-detail-trend','rival-item-detail-list','rival-item-material','rival-item-recommend-core','rival-item-recommend-trend','rival-item-recommend-top']:
     _,p=m.build_request(self.args(report=report,rival_id='item',evidence_file=e,date_type=period,date=end));self.assertEqual(p['dateType'],period);self.assertEqual(p['dateRange'],start+'|'+end)
    evidence['request']['params']['dateType']='day';Path(e).write_text(json.dumps(evidence),encoding='utf-8')
    with self.assertRaises(ValueError):m.build_request(self.args(report='rival-item-material',rival_id='item',evidence_file=e,date_type=period,date=end))
 def test_periods_do_not_allow_invalid_calendar_ranges_or_custom(self):
  with tempfile.TemporaryDirectory() as t:
   e=self.evidence(t)
   for period,end,start in [('week','2026-11-01','2026-10-26'),('month','2026-10-31','2026-10-01')]:
    for report in ['rival-shop-profile','rival-shop-crowd','rival-shop-keywords','rival-shop-products']:
     _,p=m.build_request(self.args(report=report,evidence_file=e,date_type=period,date=end));self.assertEqual(p['dateRange'],start+'|'+end)
   for period,end in [('week','2026-11-03'),('month','2026-11-03'),('recent7','2026-11-03'),('custom','2026-11-03')]:
    with self.assertRaises(ValueError):m.build_request(self.args(evidence_file=e,date_type=period,date=end))
 def test_period_annotation_keeps_wrong_dates_separate_from_native_trend_window(self):
  from tb.platforms.sycm import rival_drilldowns as r
  params={'dateType':'week','dateRange':'2026-10-26|2026-11-01'}
  s=r.annotate_period({'data_status':'ok','returned_dates':['20140916','20261101']},params);self.assertEqual(s['data_status'],'date_mismatch');self.assertEqual(s['out_of_period_dates'],['20140916']);self.assertFalse(s['period_aggregation_verified'])
  s=r.annotate_period({'data_status':'ok','trend_axes':{'rivalItem1':{'dates':['2026-10-03','2026-11-01']}}},params);self.assertEqual(s['data_status'],'ok');self.assertEqual(s['period_axis_status'],'native_trend_window_outside_requested_period')
  self.assertEqual(r.annotate_period({'data_status':'security_verification'},params)['data_status'],'security_verification')
 def test_selected_item_evidence_rejects_explicit_out_of_period_row(self):
  with tempfile.TemporaryDirectory() as t:
   e=self.evidence(t,True);d=json.loads(Path(e).read_text(encoding='utf-8'));d['raw']['data']['data'][0]['statDate']={'value':'2014-09-16'};Path(e).write_text(json.dumps(d),encoding='utf-8')
   with self.assertRaises(ValueError):m.build_request(self.args(report='rival-item-material',rival_id='item',evidence_file=e))
 def test_native_weekly_monthly_tick_frequency_is_checked_not_inferred_from_request(self):
  from tb.platforms.sycm import rival_drilldowns as r
  for period,ran,axis in [('week','2026-10-26|2026-11-01',['2026-10-18','2026-10-25','2026-11-01']),('month','2026-10-01|2026-10-31',['2026-08-31','2026-09-30','2026-10-31'])]:
   s=r.annotate_period({'data_status':'ok','trend_axes':{'x':{'dates':axis}}},{'dateType':period,'dateRange':ran});self.assertTrue(s['native_tick_frequency_verified']);self.assertFalse(s['period_aggregation_verified'])
  s=r.annotate_period({'data_status':'ok','trend_axes':{'x':{'dates':['2026-10-31','2026-11-01']}}},{'dateType':'week','dateRange':'2026-10-26|2026-11-01'});self.assertFalse(s['native_tick_frequency_verified'])

if __name__=='__main__':unittest.main()
