"""Six market pages: reuse SYCM transport and retain explicit evidence gaps."""
import json,time,re
from dataclasses import replace
from pathlib import Path
from datetime import date,datetime,timezone,timedelta
from decimal import Decimal,InvalidOperation
from .platform import SYCM
from .business_queries import trace_bridge
from ...core import transport

PAGES={'ranking':'market_rank','trend':'market_insight','search':'search_rank','recruit':'channel_goods','mining':'class_dig','insight':'class_analysis'}
REPORTS={
 'categories':('ranking','/mc/common/free/getCateInfo.json','options'),
 'price-options':('ranking','/mc/mq/mkt/priceSeg/list.json','options'),
 'shops':('ranking','/mc/mq/mkt/shop/offline/rank.json','statistics'),
 'items':('ranking','/mc/mq/mkt/item/offline/rank.json','statistics'),
 'search':('search','/mc/mq/mkt/keyword/rank/pro.json','statistics'),
 'mining':('mining','/mc/cate/mining/analysis/conclusion.json','statistics'),
 'mining-detail':('mining','/mc/cate/mining/analysis/detail.json','statistics'),
 'insight-attributes':('insight','/mc/mq/cate/insights/prop/list.json','options'),
 'insight-price':('insight','/mc/mq/mkt/cate/insights/priceseg/analysis.json','statistics'),
 'insight-prop':('insight','/mc/mq/cate/insights/prop/analysis.json','statistics'),
 'trend-update':('trend','/qscdc/queryOpenSearchCommunication.json','metadata'),
 'ai-categories':('trend','/qscdc/queryCategory.json','options'),
 'ai-styles':('trend','/qscdc/queryAggregateAttr.json','statistics'),
 'ai-features':('trend','/qscdc/queryAggregateAttr.json','statistics'),
 'ai-products':('trend','/qscdc/queryUniqueProductRank.json','statistics'),
}

def options():return json.loads(Path(__file__).with_name('market_query_options.json').read_text(encoding='utf-8'))

def period(day,date_type='day'):
 end=date.fromisoformat(day)
 if date_type not in ('day','week','month','recent7','recent30'):raise ValueError('Unsupported official market period')
 start=end
 if date_type=='week':
  if end.weekday()!=6:raise ValueError('A complete week must end on Sunday')
  start=end-timedelta(days=6)
 elif date_type=='month':
  if (end+timedelta(days=1)).month==end.month:raise ValueError('A complete month must end on its last day')
  start=end.replace(day=1)
 elif date_type in ('recent7','recent30'):start=end-timedelta(days=6 if date_type=='recent7' else 29)
 return f'{start}|{end}'

def crowd_filters(args):
 p={key:getattr(args,attr,'') or '' for key,attr in [('sex','sex'),('sexRatio','sex_ratio'),('age','age'),('ageRatio','age_ratio')]}
 for value,ratio,allowed in [('sex','sexRatio',('1','2')),('age','ageRatio',('1','2','3','4','5','6'))]:
  if bool(p[value])!=bool(p[ratio]) or p[value] and (p[value] not in allowed or p[ratio] not in ('0.2','0.4','0.5','0.6','0.8')):raise ValueError('Crowd label and official ratio must be selected together')
 return {k:v for k,v in p.items() if v}

def build_request(args,*,today=None):
 if args.report not in REPORTS:raise ValueError('Unknown fixed market report')
 module,path,kind=REPORTS[args.report];p={'marketVersion':'free'};o=options()
 seller=args.seller_type if args.seller_type is not None else -1
 date_type=getattr(args,'date_type','day');ind_type=getattr(args,'ind_type',None);crowd=crowd_filters(args)
 if date_type!='day' and args.report not in ('shops','items','search','mining','mining-detail','insight-price','insight-prop'):raise ValueError('No verified period contract on this report')
 if (ind_type or crowd) and module not in ('mining','insight'):raise ValueError('Metric/crowd selection does not apply to this report')
 if (ind_type or crowd) and args.report=='insight-attributes':raise ValueError('Attribute options do not accept metric/crowd filters')
 if ind_type and ind_type not in (('pay_ord_amt','pay_ord_cnt','supply_demand_rate') if module=='mining' else ('pay_ord_amt','pay_ord_cnt')):raise ValueError('Unsupported official category metric')
 if ind_type=='supply_demand_rate' and crowd:raise ValueError('Native supply/demand analysis does not accept crowd filters')
 if args.seller_type not in (None,-1,0,1):raise ValueError('Unknown seller type')
 if args.seller_type is not None and args.report not in ('shops','items','mining','mining-detail','insight-price','insight-prop'):
  if args.report!='price-options' or args.seller_type!=0:raise ValueError('This report does not support the requested seller-type filter')
 if getattr(args,'prop_ids','') and args.report!='insight-prop':raise ValueError('Property selection is only available for insight-prop')
 if args.rank and args.report not in ('shops','items','search'):raise ValueError('Ranking selection does not apply to this report')
 if args.report in ('categories','trend-update'):
  if args.date or args.category or args.keyword or args.price_seg!='all' or args.min_price is not None or args.max_price is not None or args.page!=1:raise ValueError('Snapshot metadata/options do not accept date, category or business filters')
  return path,p
 selected=date.fromisoformat(args.date);now=date.fromisoformat(today) if today else datetime.now(timezone(timedelta(hours=8))).date()
 if selected>=now:raise ValueError('Only complete historical days are supported')
 cate=str(args.category);info=o['categories'].get(cate)
 if not info:raise ValueError('Category must come from the official regular market dictionary; D11 IDs cannot be reused')
 if module in ('mining','insight') and not info['leaf']:raise ValueError('This report requires an official leaf category')
 if isinstance(args.page,bool) or not isinstance(args.page,int) or args.page<1 or isinstance(args.limit,bool) or not isinstance(args.limit,int) or not 1<=args.limit<=100:raise ValueError('Invalid page/limit')
 paged=args.report in ('shops','items','search','mining-detail')
 if not paged and args.page!=1:raise ValueError('This report has no verified pagination contract')
 if len(args.keyword)>100:raise ValueError('Keyword is too long')
 p.update(cateId=cate,dateType=date_type,dateRange=period(args.date,date_type))
 if args.report.startswith('ai-'):
  if selected>date.fromisoformat(o['ai_update_day']):raise ValueError('Only historical AI trend samples through '+o['ai_update_day']+' are verified; do not substitute them for current market trends')
  if cate not in {'50011740','1625','50006843','50006842','30','16','50010404'}:raise ValueError('Category not declared by official AI trend dictionary')
  if args.price_seg!='all' or args.min_price is not None or args.max_price is not None or args.keyword:raise ValueError('AI trend label/price options lack a valid sample; no guessed values')
  p.update(source='electronic_business_data',age='all',crowd='all',price='all')
  if args.report=='ai-categories':p['queryType']='style'
  if args.report in ('ai-styles','ai-features'):p.update(queryType='style' if args.report=='ai-styles' else 'feature',sortType='comprehensive_sorting',heatValue='50',styles='')
  return path,p
 if args.price_seg!='all':
  if args.report not in ('shops','items') or args.price_seg not in {str(x['priceSegId']) for x in o['price_segments'].get(cate,[])}:raise ValueError('Price segment must come from this category official dictionary')
 if args.min_price is not None or args.max_price is not None:
  if args.report!='items' or args.price_seg!='all' or args.min_price is None or args.max_price is None:raise ValueError('Custom prices require items and both bounds, without a price segment')
  try:
   lo,hi=Decimal(args.min_price),Decimal(args.max_price)
   if not lo.is_finite() or not hi.is_finite() or lo<0 or hi<lo:raise ValueError('Invalid price bounds')
  except InvalidOperation:raise ValueError('Invalid price bounds')
  p.update(minPrice=str(lo),maxPrice=str(hi))
 if args.keyword and args.report not in ('shops','items','search'):raise ValueError('No keyword filter on this report')
 if args.report in ('shops','items'):
  rank=args.rank or 'gmv'
  if rank not in (('gmv','growth') if args.report=='shops' else ('gmv','growth','flow','add','newitm_ipv','recommend_flow','growth_flow')):raise ValueError('Unknown ranking type')
  if args.report=='items' and rank in ('flow','add','recommend_flow','growth_flow'):path='/mc/mq/mkt/item/offline/rank/'+{'flow':'search','add':'purpose','recommend_flow':'recommend','growth_flow':'rise'}[rank]+'.json'
  if rank in ('recommend_flow','growth_flow'):p.update(orderBy='deepViewCtr' if rank=='recommend_flow' else 'ipvUvChangeRate',order='asc' if rank=='recommend_flow' else 'desc')
  p.update(rankType=rank,sellerType=seller,cateFlag='all',priceSeg='' if args.price_seg=='all' else args.price_seg,keyWord=args.keyword)
  if args.report=='shops':p['indexCode']='uv,saleItemCnt'
 elif args.report=='search':
  rank=args.rank or 'hot'
  if rank not in ('hot','soar','rise'):raise ValueError('Unknown keyword ranking type')
  p.update(kwType='search',rankType=rank,keyWord=args.keyword,device=0,order='desc',orderBy={'hot':'seIpvUvHits','soar':'seUvEx','rise':'seUvDelta'}[rank])
 elif args.report=='price-options':p.update(sellerType=0)
 elif args.report in ('mining','mining-detail','insight-price','insight-prop'):p.update(sellerType=seller,indType=ind_type or 'pay_ord_amt',**crowd)
 if args.report=='mining-detail':p.update(order='desc',orderBy={'pay_ord_amt':'payByrCnt','pay_ord_cnt':'payByrCnt','supply_demand_rate':'demandGrowRate'}[p['indType']] if ind_type else 'payOrdAmtRate')
 prop_ids=getattr(args,'prop_ids','')
 if args.report=='insight-prop':
  valid={str(x['id']) for x in o.get('property_options',{}).get(cate,[])};chosen=prop_ids.split(',')
  if not prop_ids or any(x not in valid for x in chosen):raise ValueError('Property IDs must come from this leaf category official options')
  p['propIds']=','.join(sorted(set(chosen)))
 elif prop_ids:raise ValueError('Property selection is only available for insight-prop')
 if paged:p.update(page=args.page,pageSize=args.limit)
 return path,p

def redact_verification(raw):
 if isinstance(raw,dict):return {k:('[omitted]' if re.search(r'token|cookie|signature|x5sec|csrf',k,re.I) else redact_verification(v)) for k,v in raw.items()}
 if isinstance(raw,list):return [redact_verification(v) for v in raw]
 if isinstance(raw,str) and ('_____tmd_____' in raw or 'x5sec' in raw or '/punish' in raw):return '[official verification URL omitted]'
 return raw

def summarize_market(raw,*,kind,day=None):
 result={'data_status':'partial','kind':kind,'complete':False,'date_verified':False}
 if isinstance(raw,dict) and ('FAIL_SYS_USER_VALIDATE' in str(raw.get('ret',[])) or any(s in json.dumps(raw,ensure_ascii=False) for s in ('_____tmd_____','x5secdata','RGV587_ERROR'))):return {**result,'data_status':'security_verification','notes':['官方安全验证；停止该查询，不自动重试、不绕过。']}
 if not isinstance(raw,dict) or raw.get('code') not in (0,'0'):return {**result,'data_status':'error'}
 if 'data' not in raw:return {**result,'data_status':'missing_payload'}
 d=raw['data']
 if kind=='metadata':return {**result,'data_status':'metadata_only','metadata':d}
 if d is None:return {**result,'data_status':'no_data'}
 if kind=='options':return {**result,'data_status':'options_only' if d else 'no_data','option_count':len(d) if isinstance(d,(list,dict)) else None}
 rows=d if isinstance(d,list) else None
 if isinstance(d,dict):
  if any(k in d for k in ('HgHp','HgLp','LgHp')):rows=[row for k in ('HgHp','HgLp','LgHp') for row in (d.get(k) or [])]
  else:
   for k in ('data','list','rows','records'):
    if isinstance(d.get(k),list):rows=d[k];break
  result['total']=d.get('recordCount',d.get('total'))
 if rows is None:return result
 dates=set()
 def walk(x):
  if isinstance(x,dict):
   for k,v in x.items():
    if k in ('statDate','ds'):
     v=v.get('value') if isinstance(v,dict) else v
     if isinstance(v,str) and len(v) in (8,10):dates.add(v.replace('-',''))
     elif k=='statDate' and isinstance(v,(int,float)) and not isinstance(v,bool) and 1000000000000<=v<=4102444800000:dates.add(datetime.fromtimestamp(v/1000,timezone(timedelta(hours=8))).strftime('%Y%m%d'))
    else:walk(v)
  elif isinstance(x,list):
   for v in x:walk(v)
 walk(rows);result.update(data_status='ok' if rows else 'no_data',row_count=len(rows),returned_dates=sorted(dates),date_verified=bool(day and dates=={day.replace('-','')}),coverage='returned_rows_only')
 if day and dates and dates!={day.replace('-','')}:result['data_status']='date_mismatch'
 result['notes']=['官方区间、指数、空值保持原样；区间中点和draw绘图值不作精确经营指标。','日期无回显时仅是请求日期；首屏/第二页不代表全量或稳定性验收。']
 return result

def collect(args):
 from .cli import load_taobao_cookies,_api_get
 if args.report.startswith('ai-') and not args.date:raise ValueError('AI historical samples require an explicit --date; latest verified data is '+options()['ai_update_day'])
 if args.report not in ('categories','trend-update') and not args.date:args.date=(datetime.now(timezone(timedelta(hours=8))).date()-timedelta(days=1)).isoformat()
 path,params=build_request(args);module,_,kind=REPORTS[args.report]
 cookies=load_taobao_cookies();client=cookies.client
 out={'source':'shopdate_symc_MCP_extension','report':args.report,'request':{'path':path,'params':params},'observed_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'status':'error','complete':False,'bridge_diagnostics':[]}
 if args.report.startswith('ai-'):out.update(time_scope='historical_AI_sample_not_current_industry_lane',official_last_update=options()['ai_update_day'])
 try:
  if not getattr(client,'_bridge_server',None):raise ValueError('MCP bridge is required')
  with trace_bridge(client._bridge_server,out['bridge_diagnostics']):
   raw=_api_get(path,{**params,'token':cookies.get('_tb_token_',''),'_':str(int(time.time()*1000))},cookies,referer='https://sycm.taobao.com/mc/free/'+PAGES[module])
  out['raw']=redact_verification(raw);out['summary']=summarize_market(raw,kind=kind,day=args.date if getattr(args,'date_type','day')=='day' else None);out['status']=out['summary']['data_status']
  if getattr(args,'date_type','day')!='day':out['summary'].update(requested_period=params['dateRange'],date_verified=False,period_axis_status='not_independently_verified')
 except Exception as error:out['error_type']=type(error).__name__;out['error']=str(error)
 finally:
  transport.release(client)
  if args.out:
   p=Path(args.out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(out if not args.out else {k:out.get(k) for k in ('report','status','summary','error','bridge_diagnostics')},ensure_ascii=False,indent=2))

def context(args):
 client=transport.make_client(replace(SYCM,min_extension='0.9.61',extension_only=True))
 try:
  client._guard()
  raw=client._bridge_server.submit({'url':'https://sycm.taobao.com/mc/free/'+PAGES[args.page],'sycm_market_context':True},45)
  response=client.session._reply(raw);out=json.loads(response.text)
  out.update(source='shopdate_symc_MCP_existing_official_page',observed_at=datetime.now(timezone(timedelta(hours=8))).isoformat())
  if args.out:
   p=Path(args.out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
  print(json.dumps(out,ensure_ascii=False,indent=2))
 finally:transport.release(client)

def register(sp):
 from . import market_deep
 market_deep.register(sp)
 from . import market_discovery
 market_discovery.register(sp)
 from . import fashion_trends
 fashion_trends.register(sp)
 p=sp.add_parser('market-context',help='只读核对已打开的市场六页实际脚本及脱敏筛选上下文；不跳转、不取Cookie、不当作统计接口')
 p.add_argument('--page',choices=tuple(PAGES),required=True);p.add_argument('--out');p.set_defaults(func=context)
 p=sp.add_parser('market-query',help='市场六页固定只读查询；已有双11查询沿用module-query；空样本及缺口见market-catalog')
 p.add_argument('--report',choices=tuple(REPORTS),required=True);p.add_argument('--category');p.add_argument('--date');p.add_argument('--page',type=int,default=1);p.add_argument('--limit',type=int,default=10);p.add_argument('--seller-type',type=int,choices=(-1,0,1),default=None);p.add_argument('--rank');p.add_argument('--price-seg',default='all');p.add_argument('--min-price');p.add_argument('--max-price');p.add_argument('--keyword',default='');p.add_argument('--prop-ids',default='');p.add_argument('--out');p.set_defaults(func=collect)
 p.add_argument('--date-type',choices=('day','week','month','recent7','recent30'),default='day',help='--date is the period end; week/month must be complete')
 p.add_argument('--ind-type',choices=('pay_ord_amt','pay_ord_cnt','supply_demand_rate'));p.add_argument('--sex',default='');p.add_argument('--sex-ratio',default='');p.add_argument('--age',default='');p.add_argument('--age-ratio',default='')
 p=sp.add_parser('market-catalog',help='市场六个子模块逐项验证和剩余缺口；不取数')
 p.set_defaults(func=lambda args:print(Path(__file__).with_name('market_query_validation.json').read_text(encoding='utf-8') if Path(__file__).with_name('market_query_validation.json').exists() else '{"status":"validation_pending"}'))
