"""Fixed official industry-lane queries, separate from the historical AI API."""
import json,re,time
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
from .business_queries import trace_bridge
from .market_queries import summarize_market,redact_verification
from ...core import transport

ROOT='/s_portal/fashion/trend/'
PATHS={'update':'/oneauth/api/v2/commDateByCode.json','categories':ROOT+'categories','filters':ROOT+'filters','rankings':ROOT+'rankings','seller-items':ROOT+'seller-items'}
UPDATE_CODE='ads_mc_fushi_shengcan_trend_list'

def load_options(args):
 o=json.loads(Path(__file__).with_name('fashion_trend_options.json').read_text(encoding='utf-8'))
 if getattr(args,'options_file',None):
  e=json.loads(Path(args.options_file).read_text(encoding='utf-8'));p=(e.get('request') or {}).get('params',{});raw=e.get('raw') or {}
  if e.get('source')!='shopdate_symc_MCP_extension' or e.get('report')!='filters' or (e.get('request') or {}).get('path')!=PATHS['filters'] or raw.get('code') not in (0,'0') or not isinstance(raw.get('data'),list):raise ValueError('Options file must be a saved MCP industry filters result')
  days=str(p.get('dateRange','')).split('|')
  if len(days)!=2 or days[0]!=days[1]:raise ValueError('Options must have an exact day')
  if args.date and args.date!=days[0]:raise ValueError('Options file date does not match query')
  o['data_date']=days[0];o['filters']={str(p.get('cate_level1_rk')):raw['data']}
 return o

def build_request(args,o,*,ranking_evidence=None):
 if args.report not in PATHS:raise ValueError('Only fixed industry lane queries are allowed')
 if isinstance(args.page,bool) or not isinstance(args.page,int) or args.page<1 or isinstance(args.limit,bool) or not isinstance(args.limit,int) or not 1<=args.limit<=100:raise ValueError('Invalid page or limit')
 p={'marketVersion':'free'};selection={}
 if args.report=='update':
  if args.date or args.category or args.trend_type or args.tag or args.price!='all' or args.shop_id or args.page!=1:raise ValueError('Update metadata does not accept business filters')
  p['code']=UPDATE_CODE;return PATHS[args.report],p,selection
 day=date.fromisoformat(args.date)
 if args.date!=o['data_date']:raise ValueError('Use options for the same official dataset date; do not guess current data availability')
 if day>=datetime.now(timezone(timedelta(hours=8))).date():raise ValueError('Only complete historical days are supported')
 p.update(dateType='day',dateRange=f'{day}|{day}')
 if args.report=='categories':
  if args.category or args.trend_type or args.tag or args.price!='all' or args.shop_id or args.page!=1:raise ValueError('Category options do not accept business filters')
  return PATHS[args.report],p,selection
 cate=str(args.category)
 if cate not in {str(c['cate_level1_id']) for c in o['categories']}:raise ValueError('Category must come from the official industry-lane dictionary')
 if args.report=='filters':
  if args.trend_type or args.tag or args.price!='all' or args.shop_id or args.page!=1:raise ValueError('Read options before selecting tags/prices')
  p['cate_level1_rk']=cate;return PATHS[args.report],p,selection
 rows=o.get('filters',{}).get(cate,[])
 if not rows:raise ValueError('No verified filter options for this category/date; read filters first')
 if args.trend_type:rows=[r for r in rows if str(r['level2_group_rk'])==str(args.trend_type) or r['level2_group_name']==args.trend_type]
 elif not args.tag:rows=[r for r in rows if str(r['level2_group_rk'])==str(rows[0]['level2_group_rk'])]
 if args.tag:rows=[r for r in rows if (r.get('tag_rk') is not None and str(r['tag_rk'])==str(args.tag)) or r['tag_name']==args.tag]
 elif rows:rows=[r for r in rows if (r.get('tag_rk'),r.get('tag_name'))==(rows[0].get('tag_rk'),rows[0].get('tag_name'))]
 if not rows:raise ValueError('Unknown trend type or tag for this category')
 bindings={(str(r['level2_group_rk']),str(r.get('tag_rk')),r['tag_name']) for r in rows}
 if len(bindings)!=1:raise ValueError('Ambiguous tag; select its trend type explicitly')
 row=rows[0];label='';price_id='all'
 if args.price!='all':
  matches=[r for r in rows if str(r['price_rk'])==str(args.price) or r['price_range']==args.price]
  if not matches:raise ValueError('Price must belong to this category, trend type and tag')
  labels={r['price_range'] for r in matches}
  if len(labels)!=1:raise ValueError('Ambiguous official price option')
  label=matches[0]['price_range'];price_id=str(matches[0]['price_rk'])
 selection={'category':cate,'type_id':str(row['level2_group_rk']),'type_name':row['level2_group_name'],'tag_id':str(row['tag_rk']) if row.get('tag_rk') is not None else None,'tag_name':row['tag_name'],'price_id':price_id,'price_label':label}
 p.update(main_cate_level1_id=cate,tag_name=row['tag_name'])
 if args.report=='rankings':
  if args.shop_id:raise ValueError('Shop selection only applies to seller-items')
  p.update(tag_price_range=label,page=args.page,pageSize=args.limit)
 else:
  if args.price!='all' or args.page!=1 or args.limit!=10:raise ValueError('Native seller-items has no price-range or pagination contract')
  e=ranking_evidence or {};ep=(e.get('request') or {}).get('params',{});raw=e.get('raw') or {};data=raw.get('data') or {};rankrows=data if isinstance(data,list) else data.get('data',[])
  if e.get('source')!='shopdate_symc_MCP_extension' or e.get('report')!='rankings' or (e.get('request') or {}).get('path')!=PATHS['rankings'] or raw.get('code') not in (0,'0') or any(ep.get(k)!=p[k] for k in ('dateRange','main_cate_level1_id','tag_name')):raise ValueError('Shop evidence must match the same date/category/tag ranking')
  if not args.shop_id or str(args.shop_id) not in {str(r.get('userId')) for r in rankrows}:raise ValueError('Shop ID must come from the matching official ranking')
  p['shop_id']=str(args.shop_id)
 return PATHS[args.report],p,selection

def collect(args):
 from .cli import load_taobao_cookies
 o=load_options(args);cookies=load_taobao_cookies();client=cookies.client
 out={'source':'shopdate_symc_MCP_extension','report':args.report,'status':'error','complete':False,'observed_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'bridge_diagnostics':[]}
 try:
  out['phase']='bridge_ready';client._guard()
  if not getattr(client,'_bridge_server',None):raise ValueError('Only the MCP extension transport is allowed')
  with trace_bridge(client._bridge_server,out['bridge_diagnostics']):
   # The bridge polls on a 30-second cadence. Give this one permitted token
   # read two polling windows; never replay the business query on timeout.
   out['phase']='token';token=client._bridge_server.submit({'cookie':'_tb_token_'},60).get('value') or ''
   if not token:raise ValueError('SYCM token unavailable; no statistics query was sent')
   def get_once(path,params):
    # Reuse the SDK builder/send/check stack, with no automatic replay.
    url,q,headers=client._build('root',path,{**params,'token':token,'_':str(int(time.time()*1000))})
    return client.send(url,q,path,{**headers,'Referer':'https://sycm.taobao.com/mc/free/market_insight'},retries=0)
   if args.report!='update' and (not args.date or args.report in ('categories','filters') and args.date!=o['data_date']):
    out['phase']='official_update';meta=get_once(PATHS['update'],{'code':UPDATE_CODE,'marketVersion':'free'});out['update_metadata']=redact_verification(meta)
    meta_summary=summarize_market(meta,kind='metadata')
    if meta_summary['data_status']=='security_verification':
     out.update(status='security_verification',summary=meta_summary);raise ValueError('Official update query requires human security verification; stopped')
    if meta.get('code') not in (0,'0') or not isinstance(meta.get('data'),dict) or not meta['data'].get('updateDay'):raise ValueError('Official industry update day is unavailable')
    official_day=date.fromisoformat(meta['data']['updateDay']).isoformat();out['official_update_day']=official_day
    if not args.date:args.date=official_day
    if args.report in ('categories','filters') and args.date==official_day:
     if o['data_date']!=official_day:o['filters']={}
     o['data_date']=official_day
   evidence=json.loads(Path(args.rankings_file).read_text(encoding='utf-8')) if getattr(args,'rankings_file',None) else None
   out['phase']='request_validation';path,params,selection=build_request(args,o,ranking_evidence=evidence);out.update(request={'path':path,'params':params},selection=selection)
   out['phase']='statistics_request';raw=get_once(path,params)
  out['raw']=redact_verification(raw);kind='metadata' if args.report=='update' else 'options' if args.report in ('categories','filters') else 'statistics'
  out['summary']=summarize_market(raw,kind=kind,day=args.date);out['status']=out['summary']['data_status'];out['phase']='validated'
 except Exception as error:out.update(error_type=type(error).__name__,error=re.sub(r'https?://\S+','[URL omitted]',str(error)))
 finally:
  transport.release(client)
  if args.out:
   p=Path(args.out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(out if not args.out else {k:out.get(k) for k in ('report','status','phase','summary','selection','error','bridge_diagnostics')},ensure_ascii=False,indent=2))

def register(sp):
 p=sp.add_parser('market-lane',help='行业趋势赛道：官方数据日、类目、标签/价格、店铺榜和店铺商品；与历史AI接口分开')
 p.add_argument('--report',choices=tuple(PATHS),required=True);p.add_argument('--date');p.add_argument('--category');p.add_argument('--type',dest='trend_type');p.add_argument('--tag');p.add_argument('--price',default='all');p.add_argument('--page',type=int,default=1);p.add_argument('--limit',type=int,default=10);p.add_argument('--shop-id');p.add_argument('--options-file');p.add_argument('--rankings-file');p.add_argument('--out');p.set_defaults(func=collect)
