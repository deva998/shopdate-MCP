"""Fixed native market drilldowns; existing market-query contracts are reused."""
import json,re,time
from types import SimpleNamespace
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
from . import market_queries as market
from .business_queries import trace_bridge
from ...core import transport
from . import rival_drilldowns

# Public source references: op-market chunks 65/67/68/69/74/76, obtained via MCP.
REPORTS={
 'config-shops':('ci_monitor','/mc/ci/free/config/rival/shop/getMonitoredListPage.json'),
 'config-items':('ci_monitor','/mc/ci/free/config/rival/item/getMonitoredListPage.json'),
 'config-groups':('ci_monitor','/mc/ci/free/config/rival/group/pageQueryGroups.json'),
 'rival-shop-options':('ci_shop','/mc/ci/free/config/rival/shop/getMonitoredListExcludeGreatShop.json'),
 'monitor-shops':('ci_monitor','/mc/ci/free/v2/shop/monitor/listShop/page.json'),
 'monitor-items':('ci_monitor','/mc/ci/free/item/monitor/list/page.json'),
 'mining-leaf':('class_dig','/mc/cate/mining/leaf/cate/detail.json'),
 'mining-items':('class_dig','/mc/cate/mining/leaf/cate/detail/item.json'),
 'mining-keywords':('class_dig','/mc/cate/mining/leaf/cate/detail/hotKeyword.json'),
 'price-detail':('class_analysis','/mc/mq/mkt/cate/insights/priceseg/analysis/detail/table.json'),
 'prop-detail':('class_analysis','/mc/mq/cate/insights/prop/detail.json'),
 'search-categories':('search_analysis','/mc/mq/mkt/keyword/cate/analysis.json'),
 'search-related':('search_analysis','/mc/mq/mkt/keyword/relate/analysis.json'),
 'search-trend':('search_analysis','/mc/mq/mkt/keyword/relate/trend.json'),
 'shop-self':('market_rank','/mc/mq/mkt/shop/offline/self.json'),
 'content-rank':('market_rank','/mc/mq/mkt/content/rank.json'),
 'rival-shop-core':('ci_shop','/mc/mq/rivalShop/analysis/getCoreIndexes.json'),
 'rival-shop-trend':('ci_shop','/mc/mq/rivalShop/analysis/getCoreTrend.json'),
 'rival-shop-flow':('ci_shop','/mc/mq/rivalShop/analysis/getFlowSource/v3.json'),
 'rival-item-core':('ci_item','/mc/mq/rivalItem/analysis/getCoreIndexes.json'),
 'rival-item-trend':('ci_item','/mc/mq/rivalItem/analysis/getCoreTrend.json'),
 'rival-item-flow':('ci_item','/mc/mq/rivalItem/analysis/getFlowSource/v3.json'),
}
CONFIG={'config-shops','config-items','config-groups','rival-shop-options'}
REPORTS.update(rival_drilldowns.REPORTS)
RIVAL_REPORTS={'rival-shop-core','rival-shop-trend','rival-shop-flow','rival-item-core','rival-item-trend','rival-item-flow'}|set(rival_drilldowns.REPORTS)
PAGED={'config-shops','config-items','config-groups','monitor-shops','monitor-items','price-detail','prop-detail','search-categories','search-related','content-rank','rival-shop-flow','rival-item-flow'}

def rival_from_evidence(args):
 file=getattr(args,'evidence_file',None);identifier=getattr(args,'rival_id',None)
 if not file or not identifier:raise ValueError('Rival ID and saved native MCP options/monitor evidence are required')
 e=json.loads(Path(file).read_text(encoding='utf-8'));is_shop=args.report.startswith('rival-shop-');expected='rival-shop-options' if is_shop else 'monitor-items'
 if e.get('source')!='shopdate_symc_MCP_extension' or e.get('report')!=expected or (e.get('request') or {}).get('path')!=REPORTS[expected][1] or (e.get('raw') or {}).get('code') not in (0,'0'):raise ValueError('Wrong native rival evidence source')
 d=e['raw'].get('data');records=d if isinstance(d,list) else d.get('data',[]) if isinstance(d,dict) else []
 if not is_shop and any((e.get('request') or {}).get('params',{}).get(k)!=v for k,v in {'dateRange':market.period(args.date,args.date_type),'dateType':args.date_type}.items()):raise ValueError('Item monitor evidence must match the requested period')
 key='userId' if is_shop else 'itemId'
 valid={str(row[key].get('value') if isinstance(row.get(key),dict) else row.get(key)) for row in records if row.get(key) is not None}
 if str(identifier) not in valid:raise ValueError('Rival object must occur in the native evidence; do not guess/decode IDs')
 if not is_shop:
  start,end=market.period(args.date,args.date_type).split('|')
  for row in records:
   rid=row.get(key);rid=rid.get('value') if isinstance(rid,dict) else rid
   if str(rid)!=str(identifier):continue
   stamp=row.get('statDate');stamp=stamp.get('value') if isinstance(stamp,dict) else stamp
   if stamp is None:continue
   if isinstance(stamp,(int,float)) and not isinstance(stamp,bool):day=datetime.fromtimestamp(stamp/1000,timezone(timedelta(hours=8))).date().isoformat()
   else:day=date.fromisoformat(str(stamp)).isoformat()
   if not start<=day<=end:raise ValueError('Selected item evidence has an out-of-period native statDate')
 return str(identifier)

def build_request(args):
 r=args.report
 if r not in REPORTS:raise ValueError('Only fixed read-only market drilldowns are allowed')
 if (getattr(args,'metric',None) is not None or getattr(args,'audience',None) is not None) and r not in rival_drilldowns.REPORTS:raise ValueError('Drilldown metric/audience does not apply to this report')
 if isinstance(args.page,bool) or not isinstance(args.page,int) or args.page<1 or isinstance(args.limit,bool) or not isinstance(args.limit,int) or not 1<=args.limit<=100:raise ValueError('Invalid page/limit')
 if r not in PAGED and (args.page!=1 or args.limit!=10):raise ValueError('This native report has no pagination contract')
 if args.cycle and r!='search-related':raise ValueError('Cycle selection only applies to related keywords')
 if args.rank and r not in ('search-related','shop-self','content-rank'):raise ValueError('Ranking selection does not apply to this report')
 if args.prop_ids and r!='prop-detail':raise ValueError('Properties only apply to property detail')
 cat_report=r.startswith('mining-') or r in ('price-detail','prop-detail','shop-self','content-rank')
 if args.category and not cat_report:raise ValueError('This native report has no category parameter')
 if args.keyword and not r.startswith('search-'):raise ValueError('Keyword selection does not apply to this report')
 category_analysis=r.startswith('mining-') or r in ('price-detail','prop-detail')
 if r in ('mining-items','mining-keywords') and market.crowd_filters(args):raise ValueError('This native child query does not carry crowd filters')
 if (getattr(args,'rival_id',None) or getattr(args,'evidence_file',None)) and r not in RIVAL_REPORTS:raise ValueError('Rival evidence only applies to rival reports')
 if (args.ind_type or market.crowd_filters(args)) and not category_analysis:raise ValueError('Metric/crowd does not apply to this report')
 if args.seller_type is not None and r not in ('monitor-shops','monitor-items','shop-self','mining-leaf','mining-items','mining-keywords','price-detail','prop-detail'):raise ValueError('Seller type does not apply to this report')
 if args.seller_type not in (None,-1,0,1):raise ValueError('Invalid seller type')
 p={'marketVersion':'free'}
 if r in CONFIG:
  if args.date or args.date_type!='day':raise ValueError('Configuration is a current snapshot, not historical statistics')
 else:
  if not args.date or date.fromisoformat(args.date)>=datetime.now(timezone(timedelta(hours=8))).date():raise ValueError('An explicit complete historical date is required')
  p.update(dateType=args.date_type,dateRange=market.period(args.date,args.date_type))
 if r in PAGED:p.update(page=args.page,pageSize=args.limit)
 if r in rival_drilldowns.REPORTS:return REPORTS[r][1],rival_drilldowns.build_params(args,rival_from_evidence(args),p)
 if category_analysis or r=='shop-self':
  base=vars(args).copy();base.update(report='insight-prop' if r=='prop-detail' else 'insight-price' if r=='price-detail' else 'mining-detail' if category_analysis else 'shops',price_seg='all',min_price=None,max_price=None,rank=None)
  # The reused builder validates category/metric choices, not the native
  # detail table's pagination. Keep the real page/pageSize already in p.
  base.update(page=1,limit=10)
  if r=='mining-keywords':
   if args.ind_type not in (None,'supply_demand_rate'):raise ValueError('Native keyword drilldown only supports supply_demand_rate')
   base['ind_type']='supply_demand_rate'
  _,bp=market.build_request(SimpleNamespace(**base))
  p.update({k:v for k,v in bp.items() if k in ('cateId','sellerType','indType','sex','sexRatio','age','ageRatio','propIds')})
  if r.startswith('mining-'):p['cateIds']=p['cateId']
  if r in ('price-detail','prop-detail'):
   indexes=['payByrCnt','payOrdAmtRate','payAmtGrowRate','dynamicPctSaleRate'] if p['indType']=='pay_ord_amt' else ['payByrCnt','payOrdQtyPct','payOrdQtyGrowRate','dynamicPctSaleRate']
   p.update(indexCode=','.join(indexes),orderBy=indexes[0],order='desc')
  if r=='shop-self':
   if args.rank not in (None,'gmv','growth'):raise ValueError('Invalid shop rank')
   p.update(rankType=args.rank or 'gmv',priceSeg='',indexCode='cateRankId,payByrCnt,saleItemCnt,uv')
 elif r.startswith('search-'):
  if not args.keyword or len(args.keyword)>100:raise ValueError('A nonempty keyword of at most 100 characters is required')
  p['keyWord']=args.keyword
  if r=='search-categories':p.update(orderBy='clickHitsRatio',order='desc')
  elif r=='search-related':
   if args.rank not in (None,'related','bluesea') or args.cycle not in (None,'cycle','yearSync'):raise ValueError('Invalid native keyword rank/cycle')
   p.update(rankType=args.rank or 'related',cycleFlag=args.cycle or 'cycle',orderBy='simWeight' if args.rank=='bluesea' else 'seIpvUvHits',order='desc')
  else:p['indexCode']='seIpvUvHits'
 elif r in ('monitor-shops','monitor-items'):p.update(sellerType=-1 if args.seller_type is None else args.seller_type,indexCode='payByrCntIndexFree,payByrCntCycleCrc,uvIndexFree,uvCycleCrc',orderBy='payByrCntIndexFree',order='desc')
 elif r=='content-rank':
  if str(args.category) not in market.options()['categories']:raise ValueError('Official category required')
  if args.rank not in ('tradeLive','flowLive','amtVideo','uvVideo','hotVideo','article'):raise ValueError('Select an official content ranking')
  p.update(cateId=str(args.category),rankType=args.rank)
 elif r in ('rival-shop-core','rival-shop-trend','rival-shop-flow','rival-item-core','rival-item-trend','rival-item-flow'):
  identifier=rival_from_evidence(args);shop=r.startswith('rival-shop-');p.update({'rivalUser1Id' if shop else 'rivalItem1Id':identifier,'rivalUser2Id' if shop else 'rivalItem2Id':''})
  if not shop:p['selfItemId']=''
  if r.endswith('-trend'):
   p['indexCode']='uv'
   if not shop:p['device']=0
  if r.endswith('-flow'):p.update(indexCode='uv',device=2)
 return REPORTS[r][1],p

def summary(raw,report,day):
 gate=market.summarize_market(raw,kind='statistics',day=day)
 if gate['data_status'] in ('error','security_verification','missing_payload','no_data'):return gate
 if report in rival_drilldowns.REPORTS:return rival_drilldowns.summarize(raw,report,day)
 shaped=raw
 d=raw.get('data') if isinstance(raw,dict) else None
 if report in ('mining-leaf','mining-items','mining-keywords') and isinstance(d,dict) and d and all(str(k).isdigit() for k in d):
  records=[row for v in d.values() for row in (v if isinstance(v,list) else [v]) if isinstance(row,dict)]
  shaped={**raw,'data':records}
 elif report=='shop-self' and isinstance(d,dict) and 'shop' in d:shaped={**raw,'data':[d]}
 elif report.startswith('rival-') and report.endswith('-core') and isinstance(d,dict) and any(k in d for k in ('rivalShop1','rivalItem1','selfShop','selfItem')):
  shaped={**raw,'data':[{'object_key':k,**v} for k,v in d.items() if isinstance(v,dict)]}
 elif report.startswith('rival-') and report.endswith('-trend') and isinstance(d,dict):
  groups={}
  for k,v in d.items():
   if not isinstance(v,dict) or not isinstance(v.get('statDate'),list) or not isinstance(v.get('uv'),dict):continue
   dates=v['statDate'];values=v['uv'].get('value')
   if not isinstance(values,list) or len(values)!=len(dates):continue
   axis=[datetime.fromtimestamp(t/1000,timezone(timedelta(hours=8))).date().isoformat() for t in dates]
   groups[k]={'points':len(values),'dates':axis}
  return {'data_status':'ok' if groups else 'partial','complete':False,'date_verified':False,'trend_axes':groups,'coverage':'native_returned_trend_points','requested_day':day}
 elif report=='search-trend' and isinstance(d,dict) and isinstance(d.get('statDate'),list):
  dates=d['statDate'];series=d.get('seIpvUvHits') or {};vals=series.get('value') if isinstance(series,dict) else None
  if not isinstance(vals,list) or len(vals)!=len(dates):return {'data_status':'partial','complete':False,'reason':'Unmatched native trend axis/values'}
  shaped={**raw,'data':[{'statDate':{'value':t},'seIpvUvHits':{'value':v}} for t,v in zip(dates,vals)]}
  s=market.summarize_market(shaped,kind='statistics');s.update(native_trend_dates=s.get('returned_dates',[]),requested_day=day,date_verified=False,trend_window='official_returned_axis');return s
 s=market.summarize_market(shaped,kind='options' if report=='rival-shop-options' else 'statistics',day=day)
 if report in CONFIG and s['data_status']=='ok':s.update(data_status='configuration_only',time_scope='current_configuration_snapshot')
 return s

def collect(args):
 from .cli import load_taobao_cookies
 path,params=build_request(args);cookies=load_taobao_cookies();client=cookies.client
 out={'source':'shopdate_symc_MCP_extension','report':args.report,'request':{'path':path,'params':params},'observed_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'status':'error','complete':False,'bridge_diagnostics':[]}
 try:
  client._guard()
  if not getattr(client,'_bridge_server',None):raise ValueError('MCP extension transport required')
  with trace_bridge(client._bridge_server,out['bridge_diagnostics']):
   token=client._bridge_server.submit({'cookie':'_tb_token_'},60).get('value') or ''
   if not token:raise ValueError('Token unavailable; no business query sent')
   url,q,h=client._build('root',path,{**params,'token':token,'_':str(int(time.time()*1000))})
   raw=client.send(url,q,path,{**h,'Referer':'https://sycm.taobao.com/mc/free/'+REPORTS[args.report][0]},retries=0)
  out['raw']=market.redact_verification(raw);out['summary']=summary(raw,args.report,args.date if args.date_type=='day' else None);out['status']=out['summary']['data_status']
  if args.date_type!='day':out['summary']=rival_drilldowns.annotate_period(out['summary'],params);out['status']=out['summary']['data_status']
 except Exception as error:out.update(error_type=type(error).__name__,error=re.sub(r'https?://\S+','[URL omitted]',str(error)))
 finally:
  transport.release(client)
  if args.out:
   p=Path(args.out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(out if not args.out else {k:out.get(k) for k in ('report','status','summary','error')},ensure_ascii=False,indent=2))

def register(sp):
 p=sp.add_parser('market-deep',help='市场固定只读下钻：搜索词、类目明细、监控列表及配置；空样本/缺口见market-catalog')
 p.add_argument('--report',choices=tuple(REPORTS),required=True);p.add_argument('--date');p.add_argument('--date-type',choices=('day','week','month','recent7','recent30'),default='day');p.add_argument('--category');p.add_argument('--page',type=int,default=1);p.add_argument('--limit',type=int,default=10);p.add_argument('--seller-type',type=int,choices=(-1,0,1));p.add_argument('--ind-type',choices=('pay_ord_amt','pay_ord_cnt','supply_demand_rate'));p.add_argument('--keyword',default='');p.add_argument('--prop-ids',default='');p.add_argument('--rank');p.add_argument('--cycle',choices=('cycle','yearSync'));p.add_argument('--sex',default='');p.add_argument('--sex-ratio',default='');p.add_argument('--age',default='');p.add_argument('--age-ratio',default='');p.add_argument('--out');p.set_defaults(func=collect)
 p.add_argument('--rival-id');p.add_argument('--evidence-file',help='Saved native MCP rival options or same-period monitor-items result')
 p.add_argument('--metric',help='Fixed native sort metric for the selected rival drilldown');p.add_argument('--audience',choices=('uv','payByrCnt'),help='Estimated visitor/buyer profile, on profile/crowd reports only')
