"""Join exact official SKU IDs: historical sales, labelled specs, current total stock."""
from collections import defaultdict
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
import hashlib,json,math
from .api_client import ROOT
from .overview import numeric,formatted
from .product_exports import METRICS,ExportReader,compare_days

def load_sku_pair(day,store,*,root=None):
 root=Path(root) if root is not None else ROOT
 paths=sorted((root/'data/jd'/store.replace(':','_')/day/'products-sku-api').glob('*/products-sku-exports/report.json'),reverse=True)
 if not paths:raise FileNotFoundError('缺少两日官方SKU导出')
 path=paths[0];saved=json.loads(path.read_text(encoding='utf-8'))
 if saved.get('store',{}).get('store_key')!=store or saved.get('dimension')!='sku' or saved.get('date')!=day:raise ValueError('SKU导出店铺、日期或维度不符')
 sources=saved['sources'];control_path=Path(sources['overview']['path'])
 if hashlib.sha256(control_path.read_bytes()).hexdigest()!=sources['overview']['sha256']:raise ValueError('SKU独立概况哈希不符')
 control=json.loads(control_path.read_text(encoding='utf-8'))
 reader=ExportReader();current=reader(sources['current']['path'],day,'sku',store)
 previous=reader(sources['previous']['path'],(date.fromisoformat(day)-timedelta(days=1)).isoformat(),'sku',store)
 for side,r in [('current',current),('previous',previous)]:
  if r['source_file']['sha256']!=sources[side]['sha256']:raise ValueError('SKU源文件哈希不符')
 expected=compare_days(current,previous,control,store)
 if expected['items']!=saved['items'] or expected.get('export_limit_reached'):raise ValueError('SKU配对报告与原始文件不符或达到上限')
 return current['items'],previous['items'],{'report_path':str(path),'sources':sources,'transaction_totals_reconciled':True}

def analyze(day,store,stock,current,previous,spu):
 rows=[];seen=set()
 for sku in stock['items']:
  identifier=sku['sku_id']
  if identifier in seen:raise ValueError('库存SKU编号重复')
  seen.add(identifier);now=current.get(identifier);before=previous.get(identifier)
  values={k:numeric((now or {}).get('metrics',{}).get(k)) for k in METRICS}
  prior={k:numeric((before or {}).get('metrics',{}).get(k)) for k in METRICS};signals=[]
  if sku['total_stock']==0 and values['成交商品件数'] is not None and values['成交商品件数']>0:signals.append('当前总库存为0且统计日有成交')
  if sku['total_stock']==0 and values['商品访客数'] is not None and values['商品访客数']>0:signals.append('当前总库存为0且统计日有访客')
  rows.append({'sku_id':identifier,'name':sku.get('name'),'merchant_sku_code':sku.get('merchant_sku_code'),
   'color':sku.get('color'),'size':sku.get('size'),'sale_attributes':sku['sale_attributes'],
   'total_stock_now':sku['total_stock'],'sales_row_present':now is not None,'current':values,'previous':prior,'signals':signals})
 def groups(key):
  grouped=defaultdict(list)
  for r in rows:grouped[r[key]].append(r)
  result=[]
  for label,items in grouped.items():
   amounts=[r['current']['成交金额'] for r in items];stocks=[r['total_stock_now'] for r in items]
   result.append({'label':label,'sku_count':len(items),'amount':sum(amounts) if all(v is not None for v in amounts) else None,
    'known_amount_sum':sum(v for v in amounts if v is not None) if any(v is not None for v in amounts) else None,
    'known_amount_skus':sum(v is not None for v in amounts),'missing_amount_skus':sum(v is None for v in amounts),
    'current_total_stock':sum(stocks) if all(v is not None for v in stocks) else None,
    'conversion_rate':None,'limitation':'仅当前状态4的SKU组合；颜色/尺码组访客未去重，不聚合SKU转化率。'})
  return result
 values=[r['current']['成交金额'] for r in rows]
 total=sum(values) if rows and all(v is not None for v in values) else None
 matched=math.isclose(total,spu['amount'],rel_tol=0,abs_tol=.01) if total is not None and numeric(spu.get('amount')) is not None else None
 return {'platform':'jd','store_key':store,'date':day,'compare_date':(date.fromisoformat(day)-timedelta(days=1)).isoformat(),
  'product_id':stock['product_id'],'module':'SKU规格库存转化诊断','status':'partial',
  'scope':'current_status_4_skus_historical_sales_with_current_stock','sku_count':len(rows),
  'matched_sales_skus':sum(r['sales_row_present'] for r in rows),'items':rows,'color_groups':groups('color'),'size_groups':groups('size'),
  'selected_sku_amount_sum':total,'spu_amount':spu.get('amount'),'selected_sku_amount_matches_spu':matched,
  'stock_captured_at':stock['captured_at'],'stock_report_path':stock.get('report_path'),
  'signals_count':sum(bool(r['signals']) for r in rows),
  'limitations':['官方SKU编号精确关联；不按标题、货号片段或规格相似度猜配。',
   '库存是当前总库存且仅skuStatusList=[4]，不是历史库存、可售库存或全部状态SKU；不能证明历史销量变化由缺货导致。',
   '未出现的销售行和空指标保留缺失，不补零；仅在所选SKU金额均已知时与SPU金额核对，金额相符不证明历史所有SKU均已覆盖。',
   '颜色和尺码只取官方modelName标注，未标注保留未知；各SKU转化率独立显示，颜色/尺码组不伪造去重转化率。']}

def stock_for_product(path,store,product):
 from .inventory import verified_snapshot
 stock=verified_snapshot(path,store)
 if stock['product_id']!=product:raise ValueError('库存快照与请求商品编号不符')
 return stock

def collect(day,store,product):
 from . import inventory,api_products
 from .product_test import load_day
 inventory.make_body(product)
 records,ownership=load_day(day,store)
 if product not in records:raise ValueError('商品不在指定日、指定店铺的已核验SPU导出中')
 base=ROOT/'data/jd'/store.replace(':','_')
 paths=sorted(base.glob('*/inventory/'+product+'/*/report.json'),reverse=True)
 try:
  if not paths:raise FileNotFoundError('缺少库存快照')
  stock=stock_for_product(paths[0],store,product)
 except (OSError,ValueError,KeyError,TypeError):
  fresh=inventory.collect(product,store,day);stock=stock_for_product(fresh['report_path'],store,product)
 try:current,previous,proof=load_sku_pair(day,store)
 except FileNotFoundError:
  api_products.collect(day,store,'sku',reuse_verified=True)
  current,previous,proof=load_sku_pair(day,store)
 # Export waits must not allow an expired stock snapshot into the result.
 stock=stock_for_product(stock['report_path'],store,product)
 report=analyze(day,store,stock,current,previous,records[product])
 ownership.pop('derived_zero_evidence',None);report['sources']={'spu':ownership,'sku':proof}
 from .order_review import context as order_context
 report['orders']=order_context(day,store)
 folder=base/day/'product-diagnosis'/product/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
 report.update(report_path=str(folder/'report.json'),markdown_path=str(folder/'report.md'))
 api_products.write_json(folder/'report.json',report);(folder/'report.md').write_text(markdown(report),encoding='utf-8')
 return {k:v for k,v in report.items() if k not in ('items','sources')}|{'items_preview':report['items'][:20],'preview_limit':20}

def markdown(r):
 def text(v):return str(v if v is not None else '未提供').replace('|','／').replace('\n',' ')
 lines=['# 京东 · SKU规格库存转化诊断',f"统计日：{r['date']}；商品：{r['product_id']}；当前库存采集：{r['stock_captured_at']}。",'',
  *['- '+s for s in r['limitations']],'',
  '| SKU | 官方颜色 | 官方尺码 | 原生规格 | 当前总库存 | 统计日金额 | 统计日访客 | SKU转化率 | 核查线索 |','|---|---|---|---|---:|---:|---:|---:|---|']
 for item in r['items']:
  m=item['current'];lines.append('| '+' | '.join([item['sku_id'],text(item['color']),text(item['size']),text(' / '.join(item['sale_attributes'])),
   text(item['total_stock_now']),formatted(m['成交金额'],'元'),formatted(m['商品访客数'],'人'),formatted(m['商品成交转化率'],'%'),text('；'.join(item['signals']))])+' |')
 lines+=['',f"匹配销售行：{r['matched_sales_skus']}/{r['sku_count']}；所选SKU金额与SPU相符：{r['selected_sku_amount_matches_spu']}。",'']
 for title,key in [('官方颜色','color_groups'),('官方尺码','size_groups')]:
  lines+=['','## '+title+'组合','仅当前状态4的SKU组合；不计算未去重的组转化率。','',
   '| 标签 | SKU数 | 当前总库存 | 统计日金额 |','|---|---:|---:|---:|']
  for group in r[key]:lines.append('| '+' | '.join([text(group['label']),str(group['sku_count']),text(group['current_total_stock']),formatted(group['amount'],'元')])+' |')
 from .order_review import markdown as order_markdown
 return '\n'.join(lines)+order_markdown(r.get('orders'))
