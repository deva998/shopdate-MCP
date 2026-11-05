import sys,unittest,json,tempfile
from unittest.mock import patch
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'components/ali'))
from tb.platforms.sycm import module_queries as m

class ModuleQueriesTests(unittest.TestCase):
 def test_market_rank_nested_cp_wrapper_and_total(self):
  def wrap(rows,total):return {'code':0,'data':{'updateTime':'2026-11-04','data':{'cpType':'cp_free','data':{'recordCount':total,'data':rows}}}}
  result=m.summarize_module(wrap([{'gmvRank':{'value':1}}],100))
  self.assertEqual(result['row_count'],1);self.assertEqual(result['total'],100)
  self.assertEqual(m.summarize_module(wrap([],0))['data_status'],'no_data')
 def test_market_zone_registry_adds_without_overwriting_existing(self):
  with tempfile.TemporaryDirectory() as folder:
   p=Path(folder)/'module_query_registry.json';p.write_text(json.dumps({'reports':{'old':{'module':'customer'}},'modules':['customer']}),encoding='utf8')
   p.with_name('market_zone_query_registry.json').write_text(json.dumps({'reports':{'new':{'module':'market'}},'modules':['market'],'excluded_or_gaps':[{'module':'market','status':'no_data'}]}),encoding='utf8')
   with patch.object(m,'REGISTRY_PATH',p):
    result=m.registry();self.assertEqual(set(result['reports']),{'old','new'});self.assertEqual(result['query_count'],2)
   p.with_name('market_zone_query_registry.json').write_text(json.dumps({'reports':{'old':{'module':'market'}}}),encoding='utf8')
   with patch.object(m,'REGISTRY_PATH',p),self.assertRaises(ValueError):m.registry()
 def test_market_only_registered_read_paths(self):
  spec={'path':'/mc/gmv/rank/shop/list.json','date_style':'snapshot','params':{'marketVersion':'none','cateId':9999991104},'paged':True}
  self.assertEqual(m.build_request(spec,None)[1]['cateId'],9999991104)
  with self.assertRaises(ValueError):m.build_request({**spec,'path':'/mc/ci/free/config/rival/shop/addToMonitored.json'},None)
 def test_realtime_contract_rejects_historical_date(self):
  spec={'path':'/csp/api/realtime/competition/self','date_style':'snapshot','params':{},'paged':False}
  self.assertEqual(m.build_request(spec,None,today='2026-11-04')[1],{})
  with self.assertRaises(ValueError):m.build_request(spec,'2026-11-03',today='2026-11-04')
 def test_shop_page_contract_is_exact_read_path(self):
  spec={'path':'/bda/new/decorate/page/analysis/getShopPageList.json','date_style':'domain','params':{'device':1,'appType':20},'paged':True}
  self.assertEqual(m.build_request(spec,'2026-11-03',today='2026-11-04')[1]['device'],1)
 def test_empty_tables_are_not_registered_success_or_zero(self):
  for raw in [{'code':0,'data':[]},{'code':200,'data':{'columns':[{'key':'x'}],'dataSource':[]}},{'code':0,'data':{'_value':[]}}]:
   self.assertEqual(m.summarize_module(raw)['data_status'],'no_data')
  self.assertEqual(m.summarize_module({'code':0,'data':{'payAmt':{'value':0}}})['data_status'],'ok')
  self.assertEqual(m.summarize_module({'code':0,'data':{'statDate':{'value':1793635200000},'payAmt':{'value':None}}})['data_status'],'partial')
  with self.assertRaises(ValueError):m.summarize_module({'code':1003,'data':[]})
 def test_request_styles_and_no_write_or_context_escape(self):
  spec={'path':'/domain/oneQuery.json','params':{'domainCode':'tao.shop.customer.overview','extMap':{'needCycleCrc':True}},'date_style':'domain','paged':False}
  path,p=m.build_request(spec,'2026-11-03',today='2026-11-04')
  self.assertEqual(p['dateRange'],'2026-11-03|2026-11-03');self.assertEqual(p['extMap'],'{"needCycleCrc":true}')
  _,p=m.build_request({**spec,'path':'/csp/api/core/monitor/list','date_style':'csp'},'2026-11-03',today='2026-11-04')
  self.assertEqual(p['startDate'],'20261103');self.assertEqual(p['dateRange'],'1d')
  for path in ['/ucc/crowd/customer/create.json','/csp/api/delete.json','https://evil.example/list']:
   with self.assertRaises(ValueError):m.build_request({**spec,'path':path},'2026-11-03',today='2026-11-04')
  with self.assertRaises(ValueError):m.build_request(spec,'2026-11-04',today='2026-11-04')
  with self.assertRaises(ValueError):m.build_request(spec,'2026-11-03',today='2026-11-04',page=2)

if __name__=='__main__':unittest.main()
