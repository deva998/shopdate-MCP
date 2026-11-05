import importlib.util
from datetime import date
from pathlib import Path
import unittest

SOURCE=Path(__file__).resolve().parents[2]/'components/ali/tb/platforms/sycm/business_queries.py'
spec=importlib.util.spec_from_file_location('queries',SOURCE)
q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)

class BusinessQueriesTests(unittest.TestCase):
 def test_video_overview_uses_official_shop_summary_not_product_list(self):
  path,p,scope=self.request('video-overview',start='2026-11-03')
  self.assertEqual(path,'/cc/video/overview.json')
  self.assertEqual(p,{'dateType':'day','dateRange':'2026-11-03|2026-11-03','belongType':'all'})
  with self.assertRaises(ValueError):self.request('video-overview',start='2026-10-28',end='2026-11-03')
  with self.assertRaises(ValueError):self.request('video-overview',device='0')
  with self.assertRaises(ValueError):self.request('video-overview',index='daysPayAmt')
 def test_video_trend_uses_native_thirty_day_axis(self):
  path,p,scope=self.request('video-trend',start='2026-11-03')
  self.assertEqual(path,'/cc/video/trend.json');self.assertEqual(p['dateType'],'recent30')
  self.assertEqual(p['dateRange'],'2026-10-05|2026-11-03')
  self.assertEqual(scope,'native_trailing_30_days')
 def test_video_summary_separates_people_times_and_validates_date(self):
  data={k:{'value':1} for k in q.VIDEO_OVERVIEW_METRICS}
  data.update(singleEffectPlayUv={'value':122249},singleEffectPlayPv={'value':295588},statDate={'value':1793635200000},sellerId={'value':1234567890},belongType={'value':'all'})
  p={'dateType':'day','dateRange':'2026-11-03|2026-11-03','belongType':'all'}
  s=q.report_summary('video-overview',{'code':0,'data':data},p)
  self.assertEqual(s['coverage'],'official_shop_video_overview');self.assertEqual(s['data_status'],'ok')
  self.assertEqual(s['metrics']['singleEffectPlayUv']['value'],122249)
  self.assertEqual(s['metrics']['singleEffectPlayPv']['value'],295588)
  data['statDate']['value']=1793548800000
  self.assertEqual(q.report_summary('video-overview',{'code':0,'data':data},p)['data_status'],'partial')
  data['singleEffectPlayPv']={}
  self.assertIn('singleEffectPlayPv',q.report_summary('video-overview',{'code':0,'data':data},p)['missing_metrics'])
 def test_video_list_never_treats_requested_size_as_returned_or_full(self):
  rows=[{'itemId':{'value':str(i)},'statDate':{'value':1793635200000},'sellerId':{'value':1234567890}} for i in range(20)]
  data={'recordCount':4983,'data':rows}
  s=q.video_list_summary(data,{'page':'1','pageSize':'100','dateRange':'2026-11-03|2026-11-03'})
  self.assertEqual(s['actual_row_count'],20);self.assertFalse(s['complete']);self.assertEqual(s['requested_page_size'],100)
  self.assertTrue(s['page_size_mismatch']);self.assertEqual(s['coverage'],'returned_product_page_only')
  self.assertEqual(s['returned_dates'],['2026-11-03'])
  self.assertEqual(q.video_list_summary({'recordCount':20,'data':rows},{'page':'1','pageSize':'20','dateRange':'2026-11-03|2026-11-03'})['complete'],True)
  rows[1]['itemId']=rows[0]['itemId']
  self.assertFalse(q.video_list_summary({'recordCount':20,'data':rows},{'page':'1','pageSize':'20','dateRange':'2026-11-03|2026-11-03'})['complete'])
  self.assertFalse(q.video_list_summary({'recordCount':20,'data':rows},{'page':'2','pageSize':'20','dateRange':'2026-11-03|2026-11-03'})['complete'])
 def test_official_chart_rule_reconstructs_periods_without_inventing_response_axis(self):
  raw={'code':0,'data':{'lastDay':'2026-10-31','self':[{'device':'pc','payBuyerCnt':[1,2]}],'diff':[{'device':'pc','payBuyerCnt':[3,4]}]}}
  s=q.report_summary('sales-trend',raw,{'dateType':'month','diff':'2'})
  self.assertEqual(s['derived_period_axis'],['2026-09','2026-10'])
  self.assertEqual(s['date_axis_status'],'verified_official_client_rule')
  self.assertNotIn('statDate',raw['data'])
  raw['data']['lastDay']='2026-11-01'
  s=q.report_summary('sales-trend',raw,{'dateType':'week','diff':'1'})
  self.assertEqual(s['derived_period_axis'],['2026-10-19|2026-10-25','2026-10-26|2026-11-01'])
 def test_refund_display_contract_does_not_promote_unused_nulls_or_conflicting_basis(self):
  row={'caseScene':{'value':'ALL'},'dateType':{},'allSucRfdAmt':{'value':None}}
  for k in ('shopSucRfdByr','shopSucRfdOrdCnt','ordRfdRate','shopRfdAmt','payAmtRfdRate'):row[k]={'value':0}
  raw={'code':0,'data':{'data':[row]}}
  s=q.report_summary('refund-close-overview',raw,{'refundDateType':'pay','dateType':'range'})
  self.assertEqual(s['data_status'],'ok');self.assertEqual(s['basis_echo_status'],'not_returned')
  self.assertIsNone(row['allSucRfdAmt']['value'])
  row['dateType']={'value':'refund'}
  self.assertEqual(q.report_summary('refund-close-overview',raw,{'refundDateType':'pay'})['data_status'],'partial')
 def test_native_shopping_sort_is_bounded_to_declared_metrics(self):
  p=self.request('marketing-method-items',method='gouwujin',sort_by='itmUv',sort_order='asc')[1]
  self.assertEqual(p['orderBy'],'itmUv');self.assertEqual(p['order'],'asc')
  with self.assertRaises(ValueError):self.request('marketing-method-items',method='gouwujin',sort_by='itemId')
 def test_custom_pagination_uses_verified_sort_without_overriding_explicit_order(self):
  options={'method':'gouwujin','period':'compareRange','sort_by':None,'sort_order':None}
  corrected=q.pagination_options('marketing-method-items',options,True)
  self.assertEqual(corrected['sort_by'],'itmUv');self.assertEqual(corrected['sort_order'],'asc')
  self.assertIsNone(options['sort_by'])
  self.assertEqual(q.pagination_options('marketing-method-items',{**options,'sort_by':'rcAmt'},True)['sort_by'],'rcAmt')
 def test_equal_value_order_changes_inside_verified_first_page_are_not_missing_rows(self):
  def r(ids):return {'code':0,'data':{'recordCount':3,'data':[{'itemId':i} for i in ids]}}
  responses=[r([1,2]),r([3]),r([2,1])]
  result=q.paginate(lambda page:responses.pop(0),'itemId',3)
  self.assertTrue(result['complete'])
 def test_explicit_calendar_periods_are_not_rolling_windows(self):
  path,p,_=self.request('sales-overview',start='2026-10-26',end='2026-11-01',period='week')
  self.assertEqual(p['dateType'],'week');self.assertEqual(p['dateRange'],'2026-10-26|2026-11-01')
  self.assertEqual(self.request('refund-close-overview',start='2026-10-01',end='2026-10-31',period='month')[1]['dateType'],'month')
  for kw in [dict(start='2026-10-27',end='2026-11-02',period='week'),dict(start='2026-10-02',end='2026-10-31',period='month'),dict(start='2026-10-01',end='2026-11-01',period='range')]:
   with self.assertRaises(ValueError):self.request('refund-close-overview',**kw)
  with self.assertRaises(ValueError):self.request('marketing-tool-overview',start='2026-10-26',end='2026-11-01',period='week')
  with self.assertRaises(ValueError):self.request('sales-detail',start='2026-10-01',end='2026-10-31',period='month')
 def test_official_custom_and_compare_ranges(self):
  p=self.request('refund-close-overview',start='2026-10-28',end='2026-11-02',period='range')[1]
  self.assertEqual(p['dateType'],'range')
  path,p,_=self.request('marketing-method-items',method='gouwujin',start='2026-10-28',end='2026-11-02',period='compareRange',compare_start='2026-10-20',compare_end='2026-10-25')
  self.assertEqual(path,'/cc/recharge/credit/activity/summary/getItemList.json')
  self.assertEqual(p['dateRange'],'2026-10-28|2026-11-02,2026-10-20|2026-10-25')
  with self.assertRaises(ValueError):self.request('marketing-method-overview',method='gouwujin',period='compareRange',start='2026-10-28',end='2026-11-02')
  with self.assertRaises(ValueError):self.request('sales-overview',period='range',start='2026-10-28',end='2026-11-02')
 def test_sales_trend_deep_filters_and_period_are_preserved(self):
  path,p,scope=self.request('sales-trend',start='2026-10-26',end='2026-11-01',period='week',compare_category_id='16',benchmark='average',index='orderAmt',device='2')
  self.assertEqual(p['indexs'],'orderAmt');self.assertEqual(p['categoryId'],'16');self.assertEqual(p['diff'],'1');self.assertEqual(p['dateType'],'week')
  self.assertEqual(p['dateRange'],'2026-10-26|2026-11-01');self.assertEqual(scope,'requested_historical_window')
  with self.assertRaises(ValueError):self.request('sales-trend',index='uv')
  with self.assertRaises(ValueError):self.request('sales-trend',category_id='16')
  with self.assertRaises(ValueError):self.request('sales-trend',compare_category_id='16')
 def test_period_response_semantics_do_not_invent_axes_or_time_basis(self):
  s=q.report_summary('sales-trend',{'code':0,'data':{'lastDay':'2026-11-01','self':[{'device':'all','payAmt':[1,2]}]}})
  self.assertEqual(s['data_status'],'partial');self.assertEqual(s['date_axis_status'],'not_returned')
  s=q.report_summary('refund-close-overview',{'code':0,'data':{'data':[{'caseScene':{'value':'ALL'},'dateType':{},'shopRfdAmt':{'value':1}}]}})
  self.assertEqual(s['data_status'],'partial')
 def test_unused_filter_options_are_not_silently_ignored(self):
  with self.assertRaises(ValueError):self.request('refund-close-overview',device='2')
  self.assertEqual(q.supported_periods('marketing-method-skus','newer'),[])
  self.assertEqual(q.supported_periods('marketing-method-item-trend','gouwujin'),[])
  s=q.summarize({'code':0,'data':{'statDate':['2026-10-01','2026-10-02'],'payAmt':[1]}})
  self.assertEqual(s['data_status'],'partial')
 def test_pagination_rejects_duplicates_and_missing_totals(self):
  def response(ids,total=3):return {'code':0,'data':{'recordCount':total,'data':[{'itemId':x} for x in ids]}}
  s=q.paginate(lambda page:response([1,2] if page==1 else [2,3]),'itemId',3)
  self.assertFalse(s['complete']);self.assertEqual(s['stop_reason'],'duplicate_entity')
  s=q.paginate(lambda page:response([1,2] if page==1 else [3]),'itemId',3)
  self.assertTrue(s['complete']);self.assertEqual(s['unique_count'],3)
  s=q.paginate(lambda page:response([],0),'itemId',3)
  self.assertTrue(s['complete']);self.assertEqual(s['pages_fetched'],1)
  s=q.paginate(lambda page:{'code':0,'data':[{'itemId':1}]},'itemId',3)
  self.assertFalse(s['complete']);self.assertEqual(s['stop_reason'],'missing_total')
  s=q.paginate(lambda page:response([page],3 if page==1 else 4),'itemId',3)
  self.assertEqual(s['stop_reason'],'total_changed')
  s=q.paginate(lambda page:response([1] if page==1 else []),'itemId',3)
  self.assertEqual(s['stop_reason'],'early_empty_page')
  calls=[]
  def fail(page):
   calls.append(page)
   if page==2:raise TimeoutError('timeout')
   return response([1])
  s=q.paginate(fail,'itemId',3)
  self.assertEqual(s['stop_reason'],'request_failed');self.assertEqual(s['pages_fetched'],1)
  self.assertEqual(calls,[1,2])
  s=q.paginate(lambda page:response([1]) if page==1 else {'code':500,'data':[]},'itemId',3)
  self.assertEqual(s['stop_reason'],'invalid_response')
  calls=[]
  def change(page):
   calls.append(page)
   return response([1] if len(calls)==1 else [2] if len(calls)==2 else [3],2)
  s=q.paginate(change,'itemId',3)
  self.assertEqual(s['stop_reason'],'first_page_changed');self.assertFalse(s['complete'])
 def test_refund_hour_axis_validation_and_null_preservation(self):
  response={'code':0,'data':{'data':{'today':{'statHour':['00'],'shopCloseRfdAmt':[0],'shopSucRfdAmt':[None],'shopAplRfdAmt':[1]},'yesterday':{'statHour':['00'],'shopCloseRfdAmt':[0],'shopSucRfdAmt':[1],'shopAplRfdAmt':[1]}}}}
  summary=q.report_summary('refund-live-trend',response)
  self.assertEqual(summary['data_status'],'partial')
  self.assertIsNone(response['data']['data']['today']['shopSucRfdAmt'][0])
 def test_daily_refunds_keep_dates_and_stop_without_retry(self):
  calls=[]
  def fetch(day):
   calls.append(day)
   if day.day==3:raise TimeoutError()
   return {'code':0,'data':{'data':[{'caseScene':{'value':'ALL'},'shopRfdAmt':{'value':None}}]}}
  r=q.daily_refunds(fetch,date(2026,11,1),date(2026,11,3))
  self.assertEqual(r['status'],'partial');self.assertEqual(r['summary']['returned_day_count'],2)
  self.assertEqual(len(calls),3)
  self.assertIsNone(r['raw_daily'][0]['raw']['data']['data'][0]['shopRfdAmt']['value'])
 def test_native_filters(self):
  p=self.request('marketing-tool-activities',tool='shopPromotion',act_range='shopPromotionPart',keyword='test')[1]
  self.assertEqual(p['actRange'],'shopPromotionPart');self.assertEqual(p['actName'],'test')
  p=self.request('marketing-tool-activities',keyword='123')[1]
  self.assertEqual(p['actId'],'123')
  with self.assertRaises(ValueError):self.request('marketing-tool-activities',act_type='2')
  path,p,_=self.request('sales-category-leaf',category_id='16')
  self.assertEqual(path,'/bda/tradinganaly/constitute/listLfCategory.json')
  self.assertEqual(p['categoryId'],'16')
 def test_refund_and_deep_contracts(self):
  self.assertEqual(self.request('refund-live-trend')[1],{'dateType':'today'})
  with self.assertRaises(ValueError):self.request('refund-live-trend',start='2026-11-03')
  self.assertEqual(self.request('refund-close-overview')[1]['refundDateType'],'pay')
  self.assertEqual(self.request('marketing-method-items',method='gouwujin')[0],'/xsite/rc/getRcItemList.json')
  with self.assertRaises(ValueError):self.request('marketing-method-skus',method='gouwujin')
  self.assertEqual(self.request('marketing-activity-grades',tool='shopPromotion',activity_id='123')[0],'/xsite/sale/getSaleToolActGradeOverall.json')
  path,p,scope=self.request('refund-close-trend',start='2026-10-28',end='2026-11-03')
  self.assertEqual(path,'/csp/api/refund/close/overview.json')
  self.assertEqual(scope,'daily_payment_cohort_series')
 def test_bridge_diagnostic_records_phase_without_secrets(self):
  class Server:
   def submit(self,job,timeout):return {'value':'secret','status':200,'text':'private','_pageTiming':{'startedAt':100,'finishedAt':125}}
  server=Server();trace=[]
  with q.trace_bridge(server,trace):
   server.submit({'cookie':'_tb_token_'},30)
   server.submit({'url':'https://sycm.taobao.com/flow/query.json?token=secret'},60)
  self.assertEqual([x['kind'] for x in trace],['cookie','request'])
  self.assertNotIn('secret',str(trace));self.assertNotIn('private',str(trace))
  self.assertEqual(trace[1]['page_elapsed_ms'],25)
 def request(self,report,**kw):return q.build_request(report,today=date(2026,11,4),**kw)
 def test_realtime_never_accepts_historical_date(self):
  with self.assertRaises(ValueError):self.request('realtime-overview',start='2026-11-03')
  path,p,scope=self.request('realtime-overview')
  self.assertEqual(path,'/ipoll/live/getFlowAndPay.json')
  self.assertEqual(scope,'current_snapshot')
 def test_official_tool_routes_and_dates(self):
  path,p,_=self.request('marketing-tool-overview',start='2026-11-03',tool='spsd4price')
  self.assertEqual(path,'/cc/sale/getSaleToolSellerOverall.json')
  self.assertEqual(p['dateRange'],'2026-11-03|2026-11-03')
  for kw in [{'start':'2026-11-04'},{'start':'2026-11-01','end':'2026-11-03'},{'tool':'remove'}]:
   with self.assertRaises(ValueError):self.request('marketing-tool-overview',**kw)
 def test_official_channels_and_required_drilldown(self):
  self.assertEqual(self.request('marketing-method-overview',method='older')[1]['channelId'],'934')
  with self.assertRaises(ValueError):self.request('marketing-activity-items')
  with self.assertRaises(ValueError):self.request('marketing-method-item-trend')
  path,p,_=self.request('marketing-activity-items',activity_id='123',tool='spsd4price')
  self.assertEqual(path,'/cc/sale/getSaleTool/detail.json')
  self.assertEqual(p['actId'],'123')
 def test_failed_and_empty_are_not_zero(self):
  with self.assertRaises(ValueError):q.summarize({'code':1003,'message':'invalid'})
  self.assertEqual(q.summarize({'code':0,'data':[]})['data_status'],'no_data')
  self.assertEqual(q.summarize({'code':0,'data':{'payAmt':0}})['data_status'],'ok')
  s=q.summarize({'code':0,'data':{'recordCount':100,'data':[{'itemId':'1'}]}})
  self.assertEqual(s['coverage'],'returned_page_only');self.assertEqual(s['total'],100)
 def test_exclusions_and_sort_enum(self):
  for report in ['realtime-promotion','realtime-visitors','marketing-save']:
   with self.assertRaises(ValueError):self.request(report)
  with self.assertRaises(ValueError):self.request('realtime-ranking',index='foo')
  with self.assertRaises(ValueError):self.request('realtime-ranking',limit=10000)
 def test_nested_success_and_failure(self):
  self.assertEqual(q.summarize({'hasError':False,'content':{'code':0,'data':{'payAmt':0}}})['data_status'],'ok')
  with self.assertRaises(ValueError):q.summarize({'hasError':True,'content':{'code':0,'data':[1]}})
  with self.assertRaises(ValueError):q.summarize({'code':0,'data':{'code':1003,'data':[]}})
  s=q.summarize({'code':0,'data':{'statDate':[1793548800000,1793635200000],'payAmt':[0,1]}})
  self.assertEqual(s['coverage'],'server_trend_window')
  self.assertEqual(s['returned_dates'],['2026-11-02','2026-11-03'])
  with self.assertRaises(ValueError):q.summarize({'code':False,'data':[1]})
  s=q.summarize({'code':0,'data':{'data':{'reordCount':50,'list':[{'itemId':1}]},'interval':60}})
  self.assertEqual(s['row_count'],1);self.assertEqual(s['official_reordCount'],50)
  self.assertIsNone(s['total'])
  s=q.summarize({'code':0,'data':{'statDate':[1793635200000,'2026-11-04'],'payAmt':[1,2]}})
  self.assertEqual(s['returned_dates'],['2026-11-03','2026-11-04'])
  with self.assertRaises(ValueError):self.request('marketing-activity-items',tool='shopPromotion',activity_id='123')
 def test_native_source_device_and_kefu_domain(self):
  self.assertEqual(self.request('realtime-cart-ranking')[1]['index'],'cartItmCnt')
  self.assertEqual(self.request('realtime-sources')[1]['device'],'2')
  with self.assertRaises(ValueError):self.request('realtime-sources',device='0')
  path,p,_=self.request('marketing-tool-trend',tool='spsd4kefu')
  self.assertEqual(path,'/domain/oneQuery.json');self.assertEqual(p['showType'],'trend')
 def test_native_sales_embedded_reports(self):
  path,p,_=self.request('sales-overview',start='2026-11-03')
  self.assertEqual(path,'/bda/tradinganaly/overview/get_summary.json')
  self.assertEqual(p['device'],'0')
  path,p,_=self.request('sales-trend',start='2026-11-03')
  self.assertEqual(p['dateRange'],'2026-10-05|2026-11-03')
  self.assertEqual(p['dateType'],'recent30')
  self.assertEqual(self.request('sales-device-structure')[0],'/bda/tradinganaly/constitute/getDeviceDetail.json')

if __name__=='__main__':unittest.main()
