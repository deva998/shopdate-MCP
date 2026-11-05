"""Fixed, read-only MTOP adapters and sanitized native QuickBI discovery."""
import json,re,time,hashlib
from html import unescape
from dataclasses import replace
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from .platform import SYCM
from .business_queries import trace_bridge
from .module_queries import summarize_module
from ...core import transport
from ...core.mtop import signed_request,check_mtop,TAOBAO_GATEWAY,TOKEN_COOKIES
from ...core.errors import RetryRequest

MTOP={
 'flash-core':('mtop.taobao.ltao.arke.business.querybyblockcode',{'blockType':'coreBlock'}),
 'flash-flow':('mtop.taobao.ltao.arke.business.querybyblockcode',{'blockType':'flowBlock'}),
 'flash-sales-trend':('mtop.taobao.ltao.arke.business.querytrenddata',{'originIndicatorType':'sellerGmv','onlyTrend':'true','compareIndicatorType':'onSaleItemCnt'}),
 'flash-flow-trend':('mtop.taobao.ltao.arke.business.querytrenddata',{'originIndicatorType':'itemIpv','onlyTrend':'true'}),
 'coins-general':('mtop.hd.marketing.seller.home',{'scenes':'[{"sceneCode":"shopGeneralInfo"}]'}),
 'coins-detail':('mtop.hd.marketing.seller.home',{'scenes':'[{"sceneCode":"shopDetailedInfo"}]'}),
}
QUICKBI={
 'collocation':'848e26b4-69f3-4566-8d66-8d583d9ce328',
 'confirmed-apparel':'6c681235-8bac-4df2-8a50-e9ed0efa641b',
 'pay-later':'aecec5c9-1717-42dc-9925-b039cc3a6dfa',
 'buy-another':'17569de1-aca6-4fd0-9d73-1fb0152a49e7',
}

QUICKBI.update({
 "bi-menu-14394": "a3d0354b-f392-4fc9-a378-fff0d14bdb1e",
 "bi-menu-14401": "d2aa0c41-f86f-4666-9b37-9ce28157e77f",
 "bi-menu-12112": "69c7598b-0e29-4d06-a9c9-cb2015e9810f",
 "bi-menu-12114": "c8653756-f542-4eb9-9517-091e38f4c789",
 "bi-menu-14322": "6af02a29-eda3-4c08-9d06-f9910c57cf8d",
 "bi-menu-12752": "31cf6605-7ee5-45b9-85b4-77e8d87b42d8",
 "bi-menu-12894": "838c97cf-5536-4ae4-9df5-fd3c982df7f4",
 "bi-menu-13508": "8962531f-56ee-4240-8870-06fe93618d44",
 "bi-menu-14403": "f65fa260-5b32-4d75-a7f5-b68631006e09",
 "bi-menu-14044": "e076ea1a-611d-4cef-8871-6f23153244e3",
 "bi-menu-13534": "65457e1b-047f-46cf-b410-06cf0c2dd61d",
 "bi-menu-14236": "14c35bab-2bec-4b72-bf62-ed22e8c3fc89",
 "bi-menu-13756": "0cb245d3-9d1e-4d5e-840f-6e2c30272164",
 "bi-menu-13758": "e0d8c17e-80b8-44ad-826b-8250de30e64e",
 "bi-menu-13759": "6e5bec91-9e51-4000-b2e3-e9404edd5726",
 "bi-menu-14128": "4528da13-5ee4-44d0-85f5-4125367ebd74",
 "bi-menu-14321": "53cb3a85-7ef3-4cdd-86c0-388a00966b02"
})

def protocol_platform(kind):
 if kind=='mtop':return replace(SYCM,hosts={**SYCM.hosts,'mtop':TAOBAO_GATEWAY},readable_cookies=TOKEN_COOKIES,extension_only=True,min_extension='0.9.54',check_payload=check_mtop)
 if kind=='quickbi':return replace(SYCM,hosts={**SYCM.hosts,'view':'https://bi.taobao.com'},launch_url='https://bi.taobao.com/robots.txt',readable_cookies=(),extension_only=True,min_extension='0.9.54')
 raise ValueError('Unknown protocol')

def mtop_request(report,day,*,today=None):
 if report not in MTOP:raise ValueError('Only registered read-only MTOP reports are allowed')
 d=date.fromisoformat(day);now=date.fromisoformat(today) if today else datetime.now(timezone(timedelta(hours=8))).date()
 if d>=now:raise ValueError('Only complete historical dates are supported')
 api,params=MTOP[report];params=dict(params);dates={'dateType':'day','dateRange':f'{d}|{d}'}
 if report.startswith('coins-'):params['params']=json.dumps(dates,separators=(',',':'))
 else:params.update(dates)
 return api,params

def quickbi_url(raw):
 data=raw
 for _ in range(6):
  if isinstance(data,dict) and 'content' in data:data=data['content'];continue
  if isinstance(data,dict) and 'data' in data:data=data['data'];continue
  break
 if not isinstance(data,str) or not data:return None
 return unescape(data)

def quickbi_metadata(raw):
 data=quickbi_url(raw)
 if not data:return {'status':'missing_payload'}
 u=urlsplit(data)
 if u.scheme!='https' or not u.hostname or u.username or u.password:raise ValueError('Only credential-free HTTPS report URLs are accepted')
 query=parse_qs(u.query,keep_blank_values=True)
 return {'status':'metadata_only','origin':u.scheme+'://'+u.netloc,'path':u.path,'has_query':bool(u.query),'query_keys':[k[:80] for k in sorted(query)],'has_fragment':bool(u.fragment),'signed_url_omitted':True}

def quickbi_page_summary(text):
 scripts=[]
 for raw in re.findall(r'<script[^>]+src=["\x27]([^"\x27]+)',text,re.I):
  u=urlsplit('https:'+raw if raw.startswith('//') else raw)
  if u.scheme=='https' and not u.username and not u.password:scripts.append(u.scheme+'://'+u.netloc+u.path)
 visible=re.sub(r'<(?:script|style)\b[^>]*>.*?</(?:script|style)>','',text,flags=re.I|re.S)
 visible=re.sub(r'<[^>]+>',' ',visible);visible=re.sub(r'https?://\S+','[URL omitted]',visible)
 visible=re.sub(r'(?i)(token|signature|ticket|sign)\s*[=:]\s*[^\s<]+',r'\1=[omitted]',visible)
 forms=[]
 for script in re.findall(r'<script\b[^>]*>(.*?)</script>',text,re.I|re.S):
  match=re.search(r'pageConfig',script)
  if match:
   fragment=script[max(0,match.start()-50):match.start()+280]
   fragment=re.sub(r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`''','<string>',fragment)
   forms.append(re.sub(r'\d+','<number>',fragment))
 return {'sha256':hashlib.sha256(text.encode()).hexdigest(),'characters':len(text),'scripts_without_queries':sorted(set(scripts)),'visible_text_excerpt':' '.join(visible.split())[:500],'bootstrap_initializer_shapes':forms[:2],
  'candidate_paths':sorted(set(re.findall(r'["\x27](/(?:api|dashboard|report|token3rd)/[A-Za-z0-9_./-]+)["\x27]',text))),
  'challenge_or_login':bool(re.search('请完成安全验证|滑块验证|type=["\x27]password',text,re.I)),
  'raw_HTML_and_signed_url_saved':False,'business_statistics_verified':False}

def quickbi_config(text):
 match=re.search(r'(?:window\.)?pageConfig\s*=\s*(\{)',text)
 if not match:return {}
 try:
  value=json.JSONDecoder().raw_decode(text[match.start(1):])[0]
  return value if isinstance(value,dict) else {}
 except ValueError:return {}

def quickbi_definition_summary(text):
 raw_def=json.loads(text)
 if not raw_def.get('success'):raise ValueError('Dashboard definition failed: '+str(raw_def.get('code') or 'unknown'))
 data=raw_def.get('data') or {};components=data.get('components') or []
 def safe(value):
  if isinstance(value,dict):return {k:('[omitted]' if re.search(r'token|signature|password|secret|csrf',k,re.I) else safe(v)) for k,v in value.items()}
  if isinstance(value,list):return [safe(v) for v in value]
  if isinstance(value,str):
   if value.lstrip().startswith(('{','[')):
    try:return safe(json.loads(value))
    except ValueError:pass
   return re.sub(r'(https?://[^\s"\x27<>?]+)\?[^\s"\x27<>]+',r'\1?[query omitted]',value)
  return value
 return {'component_count':len(components),'top_level_keys':sorted(data),'components':[{'id':v.get('id'),'componentId':v.get('componentId'),'componentType':v.get('componentType'),'keys':sorted(v),'query_descriptor':safe({k:v.get(k) for k in ('componentName','dashboardId','dataFromId','dataFromType','queryInput','queryParam','jsonSource','componentContent','fieldEnumList')})} for v in components if isinstance(v,dict)],'business_statistics_verified':False}

def summarize_quickbi_statistics(payload,day):
 result={'data_status':'partial','complete':False,'date_verified':False,'requested_date':day}
 if payload.get('success') is not True:return {**result,'data_status':'error'}
 data=payload.get('data') or {}
 if data.get('pollKey'):return {**result,'data_status':'pending','note':'官方异步结果未完成，未自动轮询。'}
 value=data.get('value') or {};rows=value.get('rows');values=value.get('values');columns=value.get('columns') or []
 labels=[c.get('cells',[{}])[0].get('value') for c in columns if isinstance(c,dict) and c.get('cells')]
 result['column_labels']=labels
 if labels!=['gmv_create','gmv_pay'] or not isinstance(rows,list) or not isinstance(values,list):return result
 result['row_count']=len(rows);result['page']=value.get('page')
 if not rows and not values:return {**result,'data_status':'no_data'}
 if len(rows)!=1 or len(values)!=1 or len(values[0])!=2:return result
 cells=rows[0].get('cells') or [];returned=[c.get('value') for c in cells]
 result['returned_dates']=returned;result['date_verified']=returned==[day.replace('-','')]
 metrics={label:v.get('v') for label,v in zip(labels,values[0]) if isinstance(v,dict)}
 try:
  if len(metrics)!=2 or not all(Decimal(str(v)).is_finite() for v in metrics.values()):return result
 except (InvalidOperation,ValueError):return result
 result['metrics']=metrics
 result['data_status']='ok' if result['date_verified'] else 'partial'
 result['note']='保留官方字段和数值精度；单日固定查询通过不等于其余筛选、周期或全报表验收。'
 return result

def summarize_mtop(raw):
 if not any(isinstance(x,str) and x.startswith('SUCCESS') for x in raw.get('ret',[])):return {'data_status':'error','complete':False,'ret':raw.get('ret',[])}
 data=raw.get('data') or {}
 if isinstance(data.get('result'),str):
  try:data=json.loads(data['result'])
  except ValueError:pass
 result=summarize_module({'code':0,'data':data})
 metrics=[];indicators=[]
 def walk(value):
  if isinstance(value,dict):
   if value.get('metricCode') and ('metricValue' in value or 'metricStringValue' in value):metrics.append({k:value[k] for k in ('metricCode','metricName','metricDesc','metricValue','metricStringValue','metricCycleCrc') if k in value})
   if value.get('indicatorType') and ('indicatorValueDouble' in value or 'trendDouble' in value):indicators.append(value)
   for v in value.values():walk(v)
  elif isinstance(value,list):
   for v in value:walk(v)
 walk(data)
 if metrics:result.update(data_status='ok',metric_count=len(metrics),metric_record_count=len(metrics),unique_metric_code_count=len(set(m['metricCode'] for m in metrics)),metrics=metrics)
 elif indicators:
  numeric=[v for row in indicators for v in [row.get('indicatorValueDouble'),*(row.get('trendDouble') or [])] if isinstance(v,(int,float)) and not isinstance(v,bool)]
  zero=bool(numeric) and all(v==0 for v in numeric)
  result.update(data_status='zero_only_sample' if zero else 'partial',indicator_count=len(indicators),indicators=indicators,all_returned_numeric_values_zero=zero)
  if any(isinstance(row.get('trendDouble'),list) and row['trendDouble'] for row in indicators):
   result['date_axis_status']='not_returned'
   if not any(isinstance(row.get('indicatorValueDouble'),(int,float)) for row in indicators):result['data_status']='partial'
 elif data:result['data_status']='partial';result['notes'].append('尚未识别业务指标结构，配置/元信息不作统计成功。')
 result['notes'].append('MTOP原始业务字段；协议成功不等于完整报表验收。')
 return result

def collect(args):
 out={'source':'shopdate_symc_MCP_extension','report':args.report,'protocol':args.protocol,'observed_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),'status':'error','complete':False}
 client=None
 try:
  if args.protocol=='quickbi':
   if args.report not in QUICKBI:raise ValueError('Unknown fixed QuickBI report')
   statistics=getattr(args,'statistics',False)
   if statistics and (args.report!='confirmed-apparel' or not getattr(args,'definition',False) or not getattr(args,'inspect_page',False) or args.date):raise ValueError('Statistics require confirmed-apparel --inspect-page --definition, using official default date only')
   from .cli import load_taobao_cookies,_api_get
   cookies=load_taobao_cookies();client=cookies.client
   if not getattr(client,'_bridge_server',None):raise ValueError('MCP bridge required')
   raw=_api_get('/adm/v3/report/custom/page.json',{'reportId':QUICKBI[args.report],'token':cookies.get('_tb_token_',''),'_':str(int(time.time()*1000))},cookies)
   out.update(metadata=quickbi_metadata(raw));out['status']=out['metadata']['status']
   if getattr(args,'inspect_page',False) and out['status']=='metadata_only':
    if out['metadata']['origin']!='https://bi.taobao.com' or out['metadata']['path']!='/token3rd/dashboard/view/pc.htm':raise ValueError('Unregistered native BI report origin/path')
    target=quickbi_url(raw)
    transport.release(client)
    plat=protocol_platform('quickbi')
    if getattr(args,'definition',False):plat=replace(plat,min_extension='0.9.57')
    if statistics:plat=replace(plat,min_extension='0.9.59')
    client=transport.make_client(plat);client._guard()
    if getattr(args,'definition',False):
     native=client._bridge_server.submit({'url':target,'bi_definition':True,**({'bi_statistics':True} if statistics else {})},160 if statistics else 110)
     out['native_auth_context_used']=native.get('auth_context_used',{})
     response=client.session._reply(native)
     try:out['definition']=quickbi_definition_summary(response.text);out['status']='definition_only'
     except ValueError:
      out['definition_response']={'http_status':response.status_code,**quickbi_page_summary(response.text)}
      out['status']='definition_response_not_verified'
     if statistics and native.get('statistics'):
      sample=dict(native['statistics']);body=sample.pop('text','');out['statistics']=sample
      try:
       payload=json.loads(body);out['statistics']['response']=payload
       summary=summarize_quickbi_statistics(payload,sample['requested_date']);out['summary']=summary
       out['status']='statistics_verified' if summary['data_status']=='ok' else 'statistics_'+summary['data_status']
      except ValueError:
       out['statistics']['response_summary']=quickbi_page_summary(body);out['status']='statistics_response_not_verified'
    else:
     response=client.session.get(target,timeout=45)
     if response.status_code!=200:raise ValueError('BI view HTTP '+str(response.status_code))
     if len(response.text)>5000000:raise ValueError('BI view exceeds bounded source limit')
     page=quickbi_page_summary(response.text);config=quickbi_config(response.text)
     page['bootstrap_config_keys']=sorted(config)
     page['bootstrap_tokens_present']={key:bool(config.get(key)) for key in ['csrfToken','accessToken']}
     out.update(page_source=page,status='official_report_unavailable' if '作品不存在' in page['visible_text_excerpt'] else 'page_metadata_only')
  else:
   day=args.date or (datetime.now(timezone(timedelta(hours=8))).date()-timedelta(days=1)).isoformat();api,data=mtop_request(args.report,day)
   plat=protocol_platform('mtop')
   client=transport.make_client(plat)
   if not getattr(client,'_bridge_server',None):raise ValueError('MCP bridge required')
   out.update(request={'api':api,'version':'1.0','params':data},time_scope='mixed_report_day_and_current_balance' if args.report.startswith('coins-') else 'requested_complete_day',requested_date=day,bridge_diagnostics=[])
   with trace_bridge(client._bridge_server,out['bridge_diagnostics']):
    for attempt in range(2):
     url,query,headers=signed_request(client,TAOBAO_GATEWAY,'/'+api+'/1.0/',data)
     try:raw=client.send(url,query,api,headers,retries=0);break
     except RetryRequest:
      if attempt:raise
   summary=summarize_mtop(raw);out.update(raw=raw,summary=summary,status=summary['data_status'])
 except Exception as error:
  out.update(status='error',error_type=type(error).__name__,error=re.sub(r'https?://\S+','[URL omitted]',str(error)))
 finally:
  if client:transport.release(client)
  if args.out:
   p=Path(args.out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps(out if not args.out else {k:out.get(k) for k in ('report','protocol','status','metadata','page_source','summary','error_type','error')},ensure_ascii=False,indent=2))

def register(sp):
 c=sp.add_parser('protocol-catalog',help='固定MTOP/QuickBI协议入口及逐项在线验收状态（不取数）')
 c.set_defaults(func=lambda args:print(Path(__file__).with_name('protocol_query_validation.json').read_text(encoding='utf8') if Path(__file__).with_name('protocol_query_validation.json').exists() else json.dumps({'status':'not_validated'})))
 p=sp.add_parser('protocol-query',help='固定只读MTOP报表/脱敏QuickBI元信息；未验证结果不视为业务接入完成')
 p.add_argument('--protocol',choices=('mtop','quickbi'),required=True);p.add_argument('--report',required=True,choices=tuple(MTOP)+tuple(QUICKBI));p.add_argument('--date');p.add_argument('--inspect-page',action='store_true');p.add_argument('--definition',action='store_true');p.add_argument('--statistics',action='store_true',help='服饰确收固定指标，使用官方默认前两天日期；不支持任意SQL或字段');p.add_argument('--out');p.set_defaults(func=collect)
