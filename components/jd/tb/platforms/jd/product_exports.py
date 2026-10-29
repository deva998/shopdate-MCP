"""Reconcile two official single-day product exports, without comparison-row limits.

Reads XLSX only. Does not acquire browser data or modify the source workbooks.
"""
import hashlib
import json
import math
from datetime import date,timedelta
from decimal import Decimal
from pathlib import Path

METRICS=('成交金额','成交商品件数','商品成交转化率','商品访客数')

def number(value,rate=False):
    if value is None or value in ('','-','--'):return None
    if isinstance(value,bool):raise ValueError('指标不能是布尔值')
    if rate and isinstance(value,str) and value.endswith('%'):value=Decimal(value[:-1])/100
    result=float(value)
    if not math.isfinite(result):raise ValueError('指标不是有限数值')
    return result

def parse_rows(rows,day,dimension):
    if dimension not in ('sku','spu'):raise ValueError('未验证的商品维度')
    rows=iter(rows);header=list(next(rows,()))
    required=['时间',dimension.upper(),dimension.upper()+'名称','成交金额','成交商品件数','成交转化率','商品访客数']
    if len(set(header))!=len(header) or any(x not in header for x in required):raise ValueError('导出列名缺失、重复或维度不符')
    items={};summary=None
    for row in rows:
        if not any(x is not None for x in row):continue
        raw=dict(zip(header,row))
        if raw['时间']!=day+'~'+day:raise ValueError('导出数据日期不匹配')
        identifier=str(raw[dimension.upper()])
        item={'name':raw[dimension.upper()+'名称'],'item_num':raw.get('货号'),
          'metrics':{'成交金额':number(raw['成交金额']),'成交商品件数':number(raw['成交商品件数']),
          '商品成交转化率':number(raw['成交转化率'],rate=True),'商品访客数':number(raw['商品访客数'])},
          'export_fields':raw}
        if identifier=='合计':
            if summary is not None:raise ValueError('多条合计行')
            summary=item;continue
        if not identifier.isdigit():raise ValueError('商品编号无效，禁止转换浮点编号')
        if identifier in items:raise ValueError('导出商品编号重复')
        items[identifier]=item
    if summary is None or not items:raise ValueError('缺少合计或商品明细')
    totals={}
    for metric,tolerance in (('成交金额',Decimal('.01')),('成交商品件数',Decimal('0'))):
        values=[item['metrics'][metric] for item in items.values()]
        if summary['metrics'][metric] is None:raise ValueError('合计核对指标缺失')
        total=sum((Decimal(str(x)) for x in values if x is not None),Decimal(0));control=Decimal(str(summary['metrics'][metric]))
        if abs(total-control)>tolerance:raise ValueError('商品明细未覆盖导出合计：'+metric)
        totals[metric]={'detail_sum':float(total),'summary':float(control),'difference':float(total-control),'missing_rows':sum(x is None for x in values)}
    return {'date':date.fromisoformat(day).isoformat(),'dimension':dimension,'items':items,'summary':summary,
       'totals_reconciled':True,'reconciliation':totals,'export_limit_reached':len(items)>=100000}

def extend_count_rate(data,records,proofs):
    """Present rows only: conserved zero units; zero buyers / positive visitors.

    Never fills positive conversion, a zero denominator, or an absent product.
    Known displayed rates must agree with customer/visitor counts before using
    that identity to derive any additional zero rates in this export.
    """
    field='成交商品件数'
    units={i:number(x['export_fields'].get(field)) for i,x in data['items'].items()}
    control=number(data['summary']['export_fields'].get(field))
    values=[v for v in units.values() if v is not None]
    conserved=not data.get('export_limit_reached') and control is not None and control>=0 and float(control).is_integer() and all(v>=0 and float(v).is_integer() for v in values) and sum((Decimal(str(v)) for v in values),Decimal(0))==Decimal(str(control))
    rate_identity_seen=False;consistent=True
    for i,item in data['items'].items():
        record=records[i];record['units']=units[i];record['conversion']=item['metrics']['商品成交转化率']
        if units[i] is None and conserved:
            record['units']=0
            proofs.setdefault(i,{})['units']={'rule':'nonnegative_integer_total_conservation','field':field,'official_total':control,'known_sum':control}
        buyers,uv=record['buyers'],record['uv'];rate=record['conversion']
        if rate is not None and (not 0<=rate<=1 or buyers is not None and uv is not None and uv>0 and buyers>uv):
            record['conversion']=None
            record.setdefault('_quality_issues',[]).append('conversion_out_of_scope')
            continue
        if rate is not None and buyers is not None and uv is not None and uv>0:
            rate_identity_seen=True
            if buyers<0 or buyers>uv or not 0<=rate<=1 or abs(rate-buyers/uv)>.000050000001:consistent=False
    if rate_identity_seen and consistent:
        for i,record in records.items():
            if record['conversion'] is None and record['buyers']==0 and record['uv'] is not None and record['uv']>0 and not record.get('_quality_issues'):
                record['conversion']=0
                proofs.setdefault(i,{})['conversion']={'rule':'zero_buyers_over_positive_visitors','buyers':0,'visitors':record['uv'],'known_displayed_rates_reconciled':True,'buyers_evidence':proofs.get(i,{}).get('buyers','official_nonempty')}


def compare_days(current,previous,overview,store):
    day=current['date'];prior=(date.fromisoformat(day)-timedelta(days=1)).isoformat()
    if overview.get('store',{}).get('store_key')!=store:raise ValueError('概况店铺不符')
    if overview.get('date')!=day or overview.get('compare_date')!=prior or previous['date']!=prior:raise ValueError('概况或导出日期不匹配')
    if current['dimension']!=previous['dimension']:raise ValueError('SPU/SKU不能混合')
    controls={m['name']:m for m in overview['metrics']}
    for metric in ('成交金额','成交商品件数'):
        for data,key in ((current,'value'),(previous,'previous')):
            value=data['summary']['metrics'][metric];control=controls.get(metric,{}).get(key)
            tolerance=.01 if metric=='成交金额' else 0
            if control is None or abs(Decimal(str(value))-Decimal(str(control)))>Decimal(str(tolerance)):
                raise ValueError('商品导出与独立交易概况不符：'+metric)
    from .product_test import derive_zero_evidence
    derived={};effective={}
    for side,data in [('current',current),('previous',previous)]:
        effective[side],derived[side]=derive_zero_evidence(data)
        extend_count_rate(data,effective[side],derived[side])
    items=[];id_field=current['dimension']+'_id'
    for identifier in dict.fromkeys([*current['items'],*previous['items']]):
        now=current['items'].get(identifier);before=previous['items'].get(identifier)
        metrics={}
        for metric in METRICS:
            value=now['metrics'][metric] if now else None;prior_value=before['metrics'][metric] if before else None
            field={'成交金额':'amount','商品访客数':'uv','成交商品件数':'units','商品成交转化率':'conversion'}.get(metric)
            if field:
                value=effective['current'][identifier][field] if now else None
                prior_value=effective['previous'][identifier][field] if before else None
            metrics[metric]={'value':value,'previous':prior_value,
              'relative_change':(value-prior_value)/prior_value if value is not None and prior_value not in (None,0) else None,
              'change_source':'两日官方导出计算'}
        items.append({id_field:identifier,'name':(now or before)['name'],'item_num':(now or before)['item_num'],
          'membership':'both' if now and before else 'current_only' if now else 'previous_only','metrics':metrics,
          'quality_issues':{side:effective[side].get(identifier,{}).get('_quality_issues',[]) for side in ('current','previous') if effective[side].get(identifier,{}).get('_quality_issues')}})
    comparable={metric:{'union_products':len(items),
        'comparable_products':sum(all(row['metrics'][metric][slot] is not None for slot in ('value','previous')) for row in items),
        'current_known_products':sum(row['metrics'][metric]['value'] is not None for row in items),
        'previous_known_products':sum(row['metrics'][metric]['previous'] is not None for row in items)} for metric in METRICS}
    money=[row['metrics']['成交金额'] for row in items if all(row['metrics']['成交金额'][slot] is not None for slot in ('value','previous'))]
    for metric in METRICS:
        field={'成交金额':'amount','商品访客数':'uv','成交商品件数':'units','商品成交转化率':'conversion'}.get(metric)
        subset=[row for row in items if all(row['metrics'][metric][slot] is not None for slot in ('value','previous'))]
        raw_count=sum(not any(field in derived[side].get(row[id_field],{}) for side in ('current','previous')) for row in subset) if field else len(subset)
        comparable[metric].update(raw_comparable_products=raw_count,derived_comparable_products=len(subset)-raw_count)
    comparable['成交金额']['active_comparable_products']=sum(r['value']!=0 or r['previous']!=0 for r in money)
    for side,slot,data in [('current','value',current),('previous','previous',previous)]:
        amount=math.fsum(r[slot] for r in money);total=data['summary']['metrics']['成交金额']
        comparable['成交金额'][side+'_comparable_amount']=amount
        comparable['成交金额'][side+'_official_amount']=total
        comparable['成交金额'][side+'_amount_share']=amount/total if total else None
    return {'platform':'jd','store':overview['store'],'date':day,'compare_date':prior,'dimension':current['dimension'],
      'derived_zero_evidence':derived,'comparable_coverage':comparable,
      'channel':'all','source':'official_single_day_exports','coverage':'exported_active_products',
      'transaction_totals_reconciled':True,'all_registered_products_complete':None,
      'current_items':len(current['items']),'previous_items':len(previous['items']),'items':items,
      'reconciliation':{'current':current['reconciliation'],'previous':previous['reconciliation']},
      'export_limit_reached':current['export_limit_reached'] or previous['export_limit_reached'],
      'notes':['两日分别导出不含对比时间，按商品编号外连接；缺少某日记录保留缺失，不擅自补0',
         'comparable_coverage区分原始完整记录与使用严格推导零值的记录；推导值不是官方原始非空值，原文不改动，逐格证据另存',
         '金额及件数明细合计与两份导出合计、独立交易概况核对通过；UV和客户数不能按商品相加当全店去重人数',
         '商品转化率来自导出百分比，通常只保留两位小数，变化由两日值计算，可能与接口未舍入值不同',
         '空件数仅按非负整数总量守恒推导0；转化率仅在已知成交客户0且访客大于0并通过显示比率核对时推导0，零访客和缺行仍未知',
         '导出只包含官方定义的有数据商品，不宣称覆盖所有在架商品；取消及售后退款字段不等于当日成交退货率']}

def load_export(path,day,dimension,store):
    from openpyxl import load_workbook
    path=Path(path)
    mall=store.removeprefix('jd:mall:')
    if not mall.isdigit() or not path.name.startswith(mall+'_商品明细_离线_不包括对比时间_汇总下载_'+day+'_'+day+'_') or path.suffix.lower()!='.xlsx':
        raise ValueError('文件名不符合指定店铺、日期和不含对比的官方导出合同')
    workbook=load_workbook(path,read_only=True,data_only=True)
    try:
        if len(workbook.worksheets)!=1:raise ValueError('预期一个官方导出工作表')
        result=parse_rows(workbook.active.values,day,dimension)
    finally:workbook.close()
    result['source_file']={'path':str(path.resolve()),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    return result

class ExportReader:
    """Per-command parse reuse; every access still checks file bytes and scope."""
    def __init__(self,*,loader=None):
        self.loader=loader or load_export;self.cache={};self.parse_count=0;self.cache_hits=0

    def __call__(self,path,day,dimension,store):
        path=Path(path);digest=hashlib.sha256(path.read_bytes()).hexdigest()
        key=(str(path.resolve()),digest,day,dimension,store)
        if key in self.cache:
            self.cache_hits+=1
            return self.cache[key]
        parsed=self.loader(path,day,dimension,store)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('解析期间商品文件发生变化')
        self.cache[key]=parsed;self.parse_count+=1
        return parsed


def save_comparison(current_path,previous_path,overview_path,day,dimension,store,*,export_loader=None):
    overview_path=Path(overview_path);overview=json.loads(overview_path.read_text(encoding='utf-8'))
    prior=(date.fromisoformat(day)-timedelta(days=1)).isoformat()
    reader=export_loader or load_export
    now=reader(current_path,day,dimension,store);before=reader(previous_path,prior,dimension,store)
    report=compare_days(now,before,overview,store)
    report['sources']={'current':now['source_file'],'previous':before['source_file'],
      'overview':{'path':str(overview_path.resolve()),'sha256':hashlib.sha256(overview_path.read_bytes()).hexdigest()}}
    folder=overview_path.parent/('products-'+dimension+'-exports');folder.mkdir(parents=True,exist_ok=True)
    output=folder/'report.json';output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    compact={k:v for k,v in report.items() if k!='items'}
    compact.update(status='ok',report_path=str(output),preview=report['items'][:5])
    return compact
