import unittest,json,io
from unittest.mock import patch
from types import SimpleNamespace
from tb.platforms.sycm import fashion_trends as f

class FashionTrendTests(unittest.TestCase):
 def args(self,**kw):
  d=dict(report='rankings',date='2026-10-31',category='16',trend_type='1',tag='2',price='all',page=1,limit=10,shop_id=None);d.update(kw);return SimpleNamespace(**d)
 def fixture(self):return {'data_date':'2026-10-31','categories':[{'cate_level1_id':'16','cate_level1_name':'女装'}],'filters':{'16':[{'level2_group_rk':1,'level2_group_name':'趋势风格','tag_rk':2,'tag_name':'板简风','price_rk':3,'price_range':'100-200'},{'level2_group_rk':1,'level2_group_name':'趋势风格','tag_rk':4,'tag_name':'静酷风','price_rk':5,'price_range':'200-500'}]}}
 def test_native_filters_use_cate_rk_and_ranking_uses_names(self):
  path,p,selection=f.build_request(self.args(price='3'),self.fixture())
  self.assertEqual(path,'/s_portal/fashion/trend/rankings');self.assertEqual(p['tag_name'],'板简风');self.assertEqual(p['tag_price_range'],'100-200');self.assertEqual(p['main_cate_level1_id'],'16');self.assertNotIn('tag_rk',p)
  _,p,_=f.build_request(self.args(report='filters',trend_type=None,tag=None),self.fixture());self.assertEqual(p['cate_level1_rk'],'16');self.assertNotIn('tag_name',p)
 def test_no_cross_tag_price_or_unverified_category(self):
  for kw in [dict(price='5'),dict(tag='4',price='3'),dict(category='50008165'),dict(date='2026-11-03'),dict(page=0),dict(limit=101),dict(trend_type='99')]:
   with self.assertRaises(ValueError,msg=str(kw)):f.build_request(self.args(**kw),self.fixture())
 def test_shop_ids_must_come_from_matching_ranking(self):
  e={'source':'shopdate_symc_MCP_extension','report':'rankings','request':{'path':f.PATHS['rankings'],'params':{'dateRange':'2026-10-31|2026-10-31','main_cate_level1_id':'16','tag_name':'板简风'}},'raw':{'code':0,'data':{'data':[{'userId':'shop-1'}]}}}
  _,p,_=f.build_request(self.args(report='seller-items',shop_id='shop-1'),self.fixture(),ranking_evidence=e);self.assertEqual(p['shop_id'],'shop-1');self.assertNotIn('tag_price_range',p)
  for kw in [dict(shop_id='shop-2'),dict(shop_id='shop-1',price='3')]:
   with self.assertRaises(ValueError):f.build_request(self.args(report='seller-items',**kw),self.fixture(),ranking_evidence=e)
  e['request']['path']='/other/ranking'
  with self.assertRaises(ValueError):f.build_request(self.args(report='seller-items',shop_id='shop-1'),self.fixture(),ranking_evidence=e)
 def test_metadata_does_not_accept_business_filters(self):
  with self.assertRaises(ValueError):f.build_request(self.args(report='update'),self.fixture())
  _,p,_=f.build_request(self.args(report='update',date=None,category=None,trend_type=None,tag=None),self.fixture());self.assertEqual(p['code'],'ads_mc_fushi_shengcan_trend_list')
 def test_bridge_is_ready_before_token_and_query_is_not_replayed(self):
  events=[]
  def token(job,timeout):
   self.assertEqual(events,['guard']);self.assertEqual(job,{'cookie':'_tb_token_'});self.assertEqual(timeout,60);events.append('token');return {'value':'PRIVATE'}
  def send(*a,**kw):
   events.append('send');self.assertEqual(kw['retries'],0);return {'code':0,'data':[]}
  client=SimpleNamespace(_bridge_server=SimpleNamespace(submit=token),_guard=lambda:events.append('guard'),_build=lambda host,path,p:('https://sycm.taobao.com'+path,p,{}),send=send)
  cookies=SimpleNamespace(client=client);args=self.args(report='filters',trend_type=None,tag=None);args.out=None;args.options_file=None;args.rankings_file=None
  with patch('tb.platforms.sycm.cli.load_taobao_cookies',return_value=cookies),patch.object(f,'load_options',return_value=self.fixture()),patch.object(f.transport,'release'),patch('sys.stdout',io.StringIO()) as output:f.collect(args)
  self.assertEqual(events,['guard','token','send']);self.assertNotIn('PRIVATE',output.getvalue())
 def test_missing_official_tag_rank_is_selected_by_name_without_inventing_id(self):
  o=self.fixture();o['filters']['16'].append({'level2_group_rk':1,'level2_group_name':'趋势风格','tag_name':'知识分子风','price_rk':3,'price_range':'100-200'})
  _,p,s=f.build_request(self.args(tag='知识分子风'),o);self.assertEqual(p['tag_name'],'知识分子风');self.assertIsNone(s['tag_id'])
  _,p,_=f.build_request(self.args(),o);self.assertEqual(p['tag_name'],'板简风')
 def test_fresh_official_day_can_refresh_options_without_editing_code(self):
  requests=[]
  def send(url,params,*a,**kw):
   requests.append(url)
   if url.endswith(f.PATHS['update']):return {'code':0,'data':{'updateDay':'2026-11-01'}}
   self.assertEqual(params['dateRange'],'2026-11-01|2026-11-01');return {'code':0,'data':[]}
  client=SimpleNamespace(_guard=lambda:None,_bridge_server=SimpleNamespace(submit=lambda *a:{'value':'PRIVATE'}),_build=lambda host,path,p:('https://sycm.taobao.com'+path,p,{}),send=send)
  args=self.args(report='filters',date=None,trend_type=None,tag=None);args.out=None;args.rankings_file=None
  with patch('tb.platforms.sycm.cli.load_taobao_cookies',return_value=SimpleNamespace(client=client)),patch.object(f,'load_options',return_value=self.fixture()),patch.object(f.transport,'release'),patch('sys.stdout',io.StringIO()) as output:f.collect(args)
  result=json.loads(output.getvalue());self.assertEqual(result['status'],'no_data');self.assertEqual(len(requests),2)
 def test_security_on_update_stops_before_any_business_query(self):
  calls=[]
  def send(*a,**kw):calls.append(a);return {'ret':['FAIL_SYS_USER_VALIDATE'],'data':{'url':'https://sycm.taobao.com/punish?x5secdata=SECRET'}}
  client=SimpleNamespace(_guard=lambda:None,_bridge_server=SimpleNamespace(submit=lambda *a:{'value':'PRIVATE'}),_build=lambda host,path,p:('https://sycm.taobao.com'+path,p,{}),send=send)
  args=self.args(report='rankings',date=None);args.out=None;args.rankings_file=None
  with patch('tb.platforms.sycm.cli.load_taobao_cookies',return_value=SimpleNamespace(client=client)),patch.object(f,'load_options',return_value=self.fixture()),patch.object(f.transport,'release'),patch('sys.stdout',io.StringIO()) as output:f.collect(args)
  result=json.loads(output.getvalue());self.assertEqual(result['status'],'security_verification');self.assertEqual(len(calls),1);self.assertNotIn('SECRET',output.getvalue())

if __name__=='__main__':unittest.main()
