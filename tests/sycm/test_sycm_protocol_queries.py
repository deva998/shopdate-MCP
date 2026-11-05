import unittest,json,io
from unittest.mock import patch,Mock
from types import SimpleNamespace
from tb.platforms.sycm import protocol_queries as p

class ProtocolTests(unittest.TestCase):
 def test_statistics_require_actual_columns_date_and_numeric_values(self):
  value={'rows':[{'cells':[{'value':'20261102'}]}],'columns':[{'cells':[{'value':'gmv_create'}]},{'cells':[{'value':'gmv_pay'}]}],'values':[[{'v':'1821733.6200000043'},{'v':'39499.59'}]]}
  payload={'success':True,'data':{'value':value}}
  result=p.summarize_quickbi_statistics(payload,'2026-11-02')
  self.assertEqual(result['data_status'],'ok');self.assertTrue(result['date_verified']);self.assertEqual(result['metrics']['gmv_pay'],'39499.59')
  self.assertEqual(p.summarize_quickbi_statistics(payload,'2026-11-03')['data_status'],'partial')
  self.assertEqual(p.summarize_quickbi_statistics({'success':True,'data':{'value':{'rows':[],'columns':value['columns'],'values':[]}}},'2026-11-02')['data_status'],'no_data')
  self.assertEqual(p.summarize_quickbi_statistics({'success':True,'data':{'pollKey':'pending'}},'2026-11-02')['data_status'],'pending')
  self.assertEqual(p.summarize_quickbi_statistics({'success':True,'data':{}},'2026-11-02')['data_status'],'partial')
 def test_definition_redacts_nested_encoded_secrets(self):
  value=p.quickbi_definition_summary(json.dumps({'success':True,'data':{'components':[{'componentContent':json.dumps({'csrfToken':'SECRET','nested':{'url':'https://bi.taobao.com/x?signature=PRIVATE'}})}]}}))
  self.assertNotIn('SECRET',json.dumps(value));self.assertNotIn('PRIVATE',json.dumps(value))
 def test_bridge_text_response_definition_is_parsed_without_json_method(self):
  result=p.quickbi_definition_summary('{"success":true,"data":{"components":[{"id":"c1","componentType":0}]}}')
  self.assertEqual(result['component_count'],1)
 def test_native_page_config_is_data_not_executable_script(self):
  config=p.quickbi_config('<script>window.pageConfig = {"csrfToken":"SECRET","accessToken":"PRIVATE"};</script>')
  self.assertEqual(config['csrfToken'],'SECRET')
  self.assertEqual(p.quickbi_config('<script>window.pageConfig = evil();</script>'),{})
 def test_native_html_encoded_report_url_is_decoded_before_fetch(self):
  raw={'data':'https://bi.taobao.com/token3rd/dashboard/view/pc.htm?accessId=x&amp;pageId=report&amp;signature=SECRET'}
  meta=p.quickbi_metadata(raw)
  self.assertEqual(meta['query_keys'],['accessId','pageId','signature'])
  self.assertEqual(p.quickbi_url(raw).count('&amp;'),0)
  self.assertNotIn('SECRET',json.dumps(meta))
 def test_zero_indicators_and_unlabelled_trends_are_separate(self):
  result=p.summarize_mtop({'ret':['SUCCESS::OK'],'data':{'value':[{'indicatorType':'sellerGmv','indicatorValueDouble':0,'trendDouble':[0]*30}]}})
  self.assertEqual(result['data_status'],'zero_only_sample')
  trend=p.summarize_mtop({'ret':['SUCCESS::OK'],'data':{'value':[{'indicatorType':'sellerGmv','trendDouble':[0]*30}]}})
  self.assertEqual(trend['data_status'],'partial');self.assertEqual(trend['date_axis_status'],'not_returned')
 def test_protocol_hosts_match_registered_bridge_destinations(self):
  self.assertEqual(p.protocol_platform('mtop').hosts['mtop'],'https://h5api.m.taobao.com/h5')
  self.assertEqual(p.protocol_platform('quickbi').hosts['view'],'https://bi.taobao.com')
  self.assertTrue(p.protocol_platform('mtop').extension_only)
 def test_failed_page_inspection_cannot_retain_metadata_success(self):
  cookies=SimpleNamespace(client=SimpleNamespace(_bridge_server=object()),get=lambda *a:'')
  args=SimpleNamespace(protocol='quickbi',report='confirmed-apparel',inspect_page=True,out=None)
  output=io.StringIO()
  with patch('tb.platforms.sycm.cli.load_taobao_cookies',return_value=cookies),patch('tb.platforms.sycm.cli._api_get',return_value={'data':'https://bi.taobao.com/token3rd/dashboard/view/pc.htm?token=SECRET'}),patch.object(p.transport,'release'),patch.object(p.transport,'make_client',side_effect=ValueError('blocked')),patch('sys.stdout',output):p.collect(args)
  result=json.loads(output.getvalue());self.assertEqual(result['status'],'error');self.assertNotIn('SECRET',output.getvalue())
 def test_fixed_read_contracts_and_dates(self):
  api,data=p.mtop_request('flash-core','2026-11-03',today='2026-11-04')
  self.assertEqual(api,'mtop.taobao.ltao.arke.business.querybyblockcode');self.assertEqual(data['blockType'],'coreBlock')
  api,data=p.mtop_request('coins-general','2026-11-03',today='2026-11-04')
  self.assertEqual(json.loads(data['params'])['dateRange'],'2026-11-03|2026-11-03')
  for name,day in [('mtop.evil.save','2026-11-03'),('flash-core','2026-11-04')]:
   with self.assertRaises(ValueError):p.mtop_request(name,day,today='2026-11-04')
 def test_metadata_does_not_expose_signed_url(self):
  v=p.quickbi_metadata({'data':'https://example.aliyun.com/view/a?token=SECRET&signature=SECRET'})
  self.assertEqual(v['origin'],'https://example.aliyun.com');self.assertNotIn('SECRET',json.dumps(v))
  for url in ['http://evil.example/a','https://u:p@evil.example/a','file:///c:/a']:
   with self.assertRaises(ValueError):p.quickbi_metadata({'data':url})
 def test_no_payload_is_not_success(self):
  self.assertEqual(p.summarize_mtop({'ret':['SUCCESS::OK'],'data':{}})['data_status'],'no_data')
  self.assertEqual(p.summarize_mtop({'ret':['FAIL_SYS_SESSION_EXPIRED'],'data':{}})['data_status'],'error')
  self.assertEqual(p.summarize_mtop({'ret':['SUCCESS::OK'],'data':{'priority':6}})['data_status'],'partial')
  summary=p.summarize_mtop({'ret':['SUCCESS::OK'],'data':{'rows':[{'metricCode':'tt_ord_amt','metricValue':'1,000.00'}]}})
  self.assertEqual(summary['data_status'],'ok');self.assertEqual(summary['metric_count'],1)

if __name__=='__main__':unittest.main()
