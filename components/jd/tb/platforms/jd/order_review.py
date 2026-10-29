"""Replay saved projected order evidence; never silently start an all-day crawl."""
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal
from pathlib import Path
import hashlib,json,re
from .api_client import ROOT
from . import orders

def load_verified(path,day,store):
 path=Path(path);saved=json.loads(path.read_text(encoding='utf-8'))
 if saved.get('platform')!='jd' or saved.get('store_key')!=store or saved.get('date')!=day:raise ValueError('订单证据店铺或日期不符')
 proofs=saved.get('query_proofs') or [saved.get('query_proof')]
 if not proofs or any(not isinstance(p,dict) for p in proofs):raise ValueError('缺少订单原文证据')
 sweeps=[[]];last_page=0
 full=saved.get('scope')=='created_day_all_pages'
 if not full and len(proofs)!=1:raise ValueError('单页订单证据数量不符')
 for p in proofs:
  body=p.get('request_body',{});page=body.get('request',{}).get('data',{}).get('current')
  identity=p.get('identity',{})
  if p.get('case')!='order-list' or p.get('date')!=day or p.get('source')!='registered-api' or identity.get('platform')!='jd' or identity.get('store_key')!=store or identity.get('merchant_identity_kind')!='official_shop_information' or str(identity.get('merchant_id'))!=saved.get('merchant_id'):raise ValueError('订单来源或官方商家映射不符')
  if body!=orders.make_body(day,page):raise ValueError('订单日期、分页或筛选请求不符')
  if full:
   if page==1 and last_page:sweeps.append([])
   raw_path=path.parent/f'sweep-{len(sweeps):02d}-page-{page:04d}-business.json'
  else:raw_path=path.parent/'response-business.json'
  raw=raw_path.read_bytes()
  if hashlib.sha256(raw).hexdigest()!=p.get('response_sha256'):raise ValueError('订单原文哈希不符')
  part=orders.parse(json.loads(raw),day,page,saved['merchant_id'],merchant_binding=identity.get('merchant_binding'),page_size=body['request']['data']['pageSize'])
  sweeps[-1].append(part);last_page=page
 expected=orders.aggregate_sweeps(sweeps) if full else sweeps[0][0]
 if expected['orders']!=saved.get('orders') or expected['total_orders']!=saved.get('total_orders') or (saved.get('complete') and not expected['complete']):raise ValueError('订单报告与原始分页不一致')
 if full and (expected['pages_read']!=saved.get('pages_read') or expected['missing_orders']!=saved.get('missing_orders')):raise ValueError('订单全量覆盖与分页证据不符')
 return {**saved,'report_path':str(path),'evidence_revalidated':True}

def analyze(report):
 rows=report['orders'];unknown=[r for r in rows if r['receivables'] is None]
 total=report.get('total_orders');ids={r['order_id'] for r in rows}
 complete=bool(report.get('complete')) and total is not None and len(ids)==len(rows)==total
 money=sum((Decimal(r['receivables']) for r in rows if r['receivables'] is not None),Decimal(0))
 dates=Counter(r['payment_confirmed_at'][:10] if r.get('payment_confirmed_at') else 'unknown' for r in rows)
 return {'platform':'jd','store_key':report['store_key'],'date':report['date'],'module':'订单证据复盘',
  'status':'ok' if complete and not unknown else 'partial','evidence_revalidated':report.get('evidence_revalidated',False),
  'order_ids_complete':complete,'official_total':total,'observed_order_records':len(rows),
  'missing_orders':total-len(ids) if total is not None else None,'unknown_receivables_records':len(unknown),
  'known_receivables_sum':format(money,'f'),'all_record_receivables_sum':format(money,'f') if complete and not unknown else None,
  'deduplicated_business_orders':None,'payment_confirmation_date_counts':dict(dates),
  'captured_status_counts':dict(Counter(r.get('status_name') or '未知' for r in rows)),
  'time_basis':'order_created_day','status_as_of':'capture_time_not_historical_day_end',
  'source_report_path':report.get('report_path'),'captured_at':report.get('captured_at'),'capture_finished_at':report.get('capture_finished_at'),
  'evidence_selection':report.get('selection'),'rejected_captures':report.get('rejected_newer_captures',report.get('rejected_captures',[])),
  'limitations':['商家应收不是买家实付或商智成交金额；金额缺失不补零。',
   '包含父/拆单记录，原始关系未采集；唯一订单编号覆盖不等于去重有效成交订单，不能推算全日取消率/付款率。',
   '按下单日选队列，付款确认日期和完成日期可能跨期；状态是采集时快照，不是历史日末状态。',
   '不将订单金额重复分摊到各SKU；已知应收合计只是订单记录口径，不能用于利润或GMV结论。']}

def latest_verified(day,store,*,root=None):
 root=Path(root) if root is not None else ROOT
 if not re.fullmatch(r'jd:mall:\d+',store):raise ValueError('必须指定京东店铺')
 paths=sorted((root/'data/jd'/store.replace(':','_')/day/'order-list').glob('*/report.json'),reverse=True)
 if not paths:raise FileNotFoundError('没有指定日已保存订单；不会自动抓取整日订单')
 partial=None;rejected=[]
 for path in paths:
  try:report=load_verified(path,day,store)
  except (OSError,ValueError,KeyError,TypeError) as error:
   rejected.append({'path':str(path),'error':str(error)});continue
  if report.get('complete'):
   return {**report,'selection':'latest_verified_complete','rejected_newer_captures':rejected}
  if partial is None:partial=report
 if partial is not None:return {**partial,'selection':'latest_verified_partial','rejected_captures':rejected}
 raise ValueError('所有订单证据均未通过重新核验：'+str(rejected))

def context(day,store,*,weekly=False,root=None):
 from .analysis_context import window
 reports=[];errors=[]
 for selected in window(day,14 if weekly else 1):
  try:reports.append(analyze(latest_verified(selected,store,root=root)))
  except (OSError,ValueError,KeyError,TypeError) as error:errors.append({'date':selected,'error':str(error)})
 return {'status':'partial' if reports else 'missing','scope':'saved_created_day_orders_only','reports':reports,'errors':errors,
  'next_calls':[{'platform':'jd','store':store,'command':'order-list','args':['--date',e['date'],'--all-pages']} for e in errors],
  'limitation':'仅复用同店同日原文重验后的订单；缺日不借用其他日期，不自动重抓整日订单，不从部分页推算全店经营比率。'}

def collect(day,store,path=None):
 from .api_products import write_json
 report=analyze(load_verified(path,day,store) if path else latest_verified(day,store))
 folder=ROOT/'data/jd'/store.replace(':','_')/day/'order-review'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
 report.update(report_path=str(folder/'report.json'),markdown_path=str(folder/'report.md'))
 write_json(folder/'report.json',report);(folder/'report.md').write_text(markdown({'reports':[report]}),encoding='utf-8')
 return report

def markdown(context):
 if not context:return ''
 lines=['','## 已保存订单证据复盘','金额、拆单和时间口径独立保留；不替代商智销售指标。',
  '| 下单日 | 唯一编号覆盖完整 | 记录数/官方总数 | 应收缺失记录 | 已知应收记录合计 |','|---|---|---:|---:|---:|']
 for r in context.get('reports',[]):lines.append(f"| {r['date']} | {r['order_ids_complete']} | {r['observed_order_records']}/{r['official_total']} | {r['unknown_receivables_records']} | {r['known_receivables_sum']} |")
 for e in context.get('errors',[]):lines.append('- '+e['date']+'：'+e['error'])
 if context.get('reports'):lines+=['',*['- '+s for s in context['reports'][0]['limitations']]]
 return '\n'.join(lines)+'\n'
