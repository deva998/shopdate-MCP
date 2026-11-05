"""Incremental customer/content/service queries. Existing transport and validators are reused."""
import json,re,time
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
from .business_queries import summarize,trace_bridge

REGISTRY_PATH=Path(__file__).with_name('module_query_registry.json')
WRITE=re.compile(r'(^|[/._-])(create|add|save|update|delete|remove|submit|send|publish|upload|bind|unbind|issue)([/._-]|$)',re.I)
def registry():
 data=json.loads(REGISTRY_PATH.read_text(encoding='utf8')) if REGISTRY_PATH.is_file() else {'reports':{},'excluded_or_gaps':[]}
 extra=REGISTRY_PATH.with_name('market_zone_query_registry.json')
 if extra.is_file():
  addition=json.loads(extra.read_text(encoding='utf8'));duplicate=set(data['reports'])&set(addition.get('reports',{}))
  if duplicate:raise ValueError('Duplicate registered report names: '+','.join(sorted(duplicate)))
  data['reports'].update(addition.get('reports',{}));data['modules']=list(dict.fromkeys(data.get('modules',[])+addition.get('modules',[])))
  data.setdefault('excluded_or_gaps',[]).extend(addition.get('excluded_or_gaps',[]))
  data['market_zone_validation']={k:v for k,v in addition.items() if k not in ('reports','excluded_or_gaps')}
 data['query_count']=len(data['reports'])
 return data

def build_request(spec,day,*,today=None,page=1,limit=10):
 path=spec['path']
 if not isinstance(path,str) or not (path.startswith(('/csp/api/','/s_content/','/portal/profile/','/domain/oneQuery.json','/mc/bybt/sellerData/','/mc/jhs/sellerData/','/mc/seckill/sellerData/','/mc/gmv/rank/')) or path in ('/bda/new/decorate/page/analysis/getShopPageList.json','/flow/v2/decorate/page/analysis/getShopPageList.json')) or '?' in path or '..' in path or WRITE.search(path):raise ValueError('Only registered fixed read paths are permitted')
 if not isinstance(page,int) or isinstance(page,bool) or page<1 or not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=100:raise ValueError('Invalid pagination')
 if page!=1 and not spec.get('paged'):raise ValueError('该查询没有分页契约')
 snapshot=spec['date_style']=='snapshot'
 if snapshot and day is not None:raise ValueError('实时快照不接受历史日期')
 selected=None if snapshot else date.fromisoformat(day);last_day=date.fromisoformat(today) if today else datetime.now(timezone(timedelta(hours=8))).date()
 if selected is not None and selected>=last_day:raise ValueError('Only complete historical dates are supported')
 p={k:json.dumps(v,ensure_ascii=False,separators=(',',':')) if isinstance(v,(dict,list)) else str(v).lower() if isinstance(v,bool) else v for k,v in spec.get('params',{}).items()}
 if any(k.lower() in ('token','cookie','headers','authorization','method','body') for k in p):raise ValueError('Request credentials and write controls cannot come from query definitions')
 if spec['date_style']=='csp':p.update(dateType='day',dateRange='1d',startDate=selected.strftime('%Y%m%d'),endDate=selected.strftime('%Y%m%d'))
 elif spec['date_style']=='domain':p.update(dateType='day',dateRange=f'{selected}|{selected}')
 elif snapshot:pass
 else:raise ValueError('Unknown date contract')
 if spec.get('paged'):
  p['pageNo' if 'pageNo' in p else 'page']=page;p['pageSize']=limit
 return path,p

def summarize_module(response):
 result=summarize(response)
 envelope=response.get('content',response) if isinstance(response,dict) else response
 data=envelope.get('data')
 for _ in range(6):
  if isinstance(data,dict) and 'code' in data:data=data.get('data');continue
  if isinstance(data,dict) and isinstance(data.get('data'),dict) and set(data)<= {'data','interval','timestamp','updateTime','cpType'}:data=data['data'];continue
  break
 rows=None
 if isinstance(data,list):rows=data
 elif isinstance(data,dict):
  for key in ('dataSource','data','rows','list','records','_value'):
   if isinstance(data.get(key),list):rows=data[key];break
 if rows is not None:
  result.update(row_count=len(rows),coverage='returned_rows_only',data_status='ok' if rows else 'no_data',complete=False)
  if isinstance(data,dict):
   total=data.get('recordCount',data.get('total'))
   if isinstance(total,int) and not isinstance(total,bool):result['total']=total
 elif isinstance(data,bool):result.update(data_status='partial',notes=['布尔权限/状态不是业务统计，不能视为已接入数据。'])
 elif data not in (None,{},[]):
  def count_numeric(value,key=''):
   if key.lower() in ('statdate','sellerid','userid','accountid','dateid','timestamp','interval','updatetime'):return 0
   if isinstance(value,(int,float)) and not isinstance(value,bool):return 1
   if isinstance(value,dict):return sum(count_numeric(v,k) for k,v in value.items())
   if isinstance(value,list):return sum(count_numeric(v,key) for v in value)
   return 0
  count=count_numeric(data);result['numeric_value_count']=count
  if not count:result['data_status']='partial';result['notes'].append('只返回元信息或缺失指标，不把它当作非空业务统计。')
 result['notes'].append('保留官方字段、单位、空值及比较对象；本次日样本/首屏不代表全部子页、周期或分页全量。')
 return result

def collect(args):
 from .cli import load_taobao_cookies,_api_get
 from ...core import transport
 reports=registry()['reports']
 if args.report not in reports:raise ValueError('未登记或官方空数据的查询不开放')
 spec=reports[args.report];day=args.date if spec['date_style']=='snapshot' else args.date or (datetime.now(timezone(timedelta(hours=8))).date()-timedelta(days=1)).isoformat()
 path,params=build_request(spec,day,page=args.page,limit=args.limit)
 cookies=load_taobao_cookies();client=cookies.client
 referer='https://sycm.taobao.com'+{'customer':'/cc/customer/overview','content':'/xsite/contentanalysis/lives/performance','service':'/qos/service/core_monitor/new','market':'/mc/free/d11_market_rank','business-zone':'/xsite/frame/bybt'}[spec['module']]
 result={'source':'shopdate_symc_MCP_extension','observed_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'report':args.report,'module':spec['module'],
  'request':{'path':path,'params':params,'referer':referer},'time_scope':'current_snapshot' if spec['date_style']=='snapshot' else 'complete_historical_day','source_basis':spec.get('source_file'),'status':'error'}
 try:
  if not getattr(client,'_bridge_server',None):raise ValueError('Only MCP extension-backed collection is allowed')
  result['bridge_diagnostics']=[]
  with trace_bridge(client._bridge_server,result['bridge_diagnostics']):
   result['phase']='token_read';token=cookies.get('_tb_token_','');result['phase']='api_request'
   raw=_api_get(path,{**params,'token':token,'_':str(int(time.time()*1000))},cookies,referer=referer)
  result['phase']='response_validation';result['raw']=raw;result['summary']=summarize_module(raw);result['status']=result['summary']['data_status']
 except Exception as error:result['error']=str(error);raise
 finally:
  if args.out:
   p=Path(args.out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
  transport.release(client)
 print(json.dumps({'report':args.report,'status':result['status'],'summary':result['summary'],'out':args.out} if args.out else result,ensure_ascii=False,indent=2))

def catalog(args):
 data=registry();reports=data.pop('reports',{})
 data['reports']={name:{k:spec[k] for k in ('module','label','path','date_style','paged','validated_date')} for name,spec in reports.items() if not args.module or spec['module']==args.module}
 print(json.dumps(data,ensure_ascii=False,indent=2))
def register(sp):
 c=sp.add_parser('module-catalog',help='客户、内容、服务、市场、业务专区：增量接口及已有/空表/缺口目录')
 c.add_argument('--module',choices=('customer','content','service','market','business-zone'));c.set_defaults(func=catalog)
 p=sp.add_parser('module-query',help='已核验非空的客户、内容、服务、市场、业务专区只读查询（复用现有链路）')
 p.add_argument('--report',choices=tuple(registry()['reports']),required=True);p.add_argument('--date')
 p.add_argument('--page',type=int,default=1);p.add_argument('--limit',type=int,default=10);p.add_argument('--out');p.set_defaults(func=collect)
