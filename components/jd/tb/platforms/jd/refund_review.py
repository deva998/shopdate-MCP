"""Refund-event trends; no payment-cohort return rate without linked evidence."""
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
import json,hashlib
from .api_client import ROOT

FIELDS=('退款金额','发货前-退款金额','未收货-退款金额','已收货-退款金额','已收货-退货退款金额')

def analyze(reports,day,store,*,weekly=False):
    from .daily import validate_window
    normalized=[{**row,'metrics':[{**m,'field':m.get('field',m['name']),'unit':m.get('unit','元')} for m in row['metrics']]} for row in reports]
    rows,_,_=validate_window(normalized,day,store,14 if weekly else 7)
    tables=[{m['name']:m for m in row['metrics']} for row in rows]
    metrics={}
    def total(values):
        return float(sum((Decimal(str(v)) for v in values),Decimal(0))) if all(type(v) in (int,float) and v>=0 for v in values) else None
    for name in FIELDS:
        current=total([t.get(name,{}).get('value') for t in tables[-7:]]) if weekly else tables[-1].get(name,{}).get('value')
        previous=total([t.get(name,{}).get('value') for t in tables[:7]]) if weekly else tables[-1].get(name,{}).get('previous')
        metrics[name]={'current':current,'previous':previous,'relative_change':(current-previous)/previous if current is not None and previous not in (None,0) else None,'unit':'元'}
    parts=total([metrics[name]['current'] for name in FIELDS[1:]]);overall=metrics['退款金额']['current']
    difference=overall-parts if overall is not None and parts is not None else None
    leaders=sorted(({'stage':name,**metrics[name]} for name in FIELDS[1:] if metrics[name]['current'] is not None),key=lambda r:-r['current'])
    return {'platform':'jd','store_key':store,'date':day,'module':'退货归因','status':'partial',
        'acquisition':'validated_overview_refund_events','period':'seven_vs_seven' if weekly else 'day_vs_previous',
        'metrics':metrics,'trend':[{'date':r['date'],**{name:t.get(name,{}).get('value') for name in FIELDS}} for r,t in zip(rows,tables)],
        'event_metrics_complete':all(m[slot] is not None for m in metrics.values() for slot in ('current','previous')),
        'component_reconciliation':{'official_total':overall,'component_sum':parts,'difference':difference,'matches':difference is not None and abs(difference)<=.01,'definition':'仅核对数值；不强制补齐差额或据此认定各字段必然互斥穷尽'},
        'stage_ranking':leaders,'reason_distribution':None,'item_refund_hotspots':None,'original_payment_date_distribution':None,
        'cohort_return_rate':None,'net_sales':None,'refund_loss':None,
        'missing_sources':['完整售后服务单及状态/退款成功口径','真实原因和商品关联','原订单付款批次及同批次支付件数/订单数','成熟观察窗及重复服务单/部分退款关系'],
        'actions':[{'action':'核查'+leaders[0]['stage']+'对应服务单原因与原付款日期','evidence':leaders[0]}] if leaders else [],
        'sources':[{'date':r['date'],'report_path':r.get('report_path'),'response_sha256':r.get('response_sha256')} for r in rows],
        'limitations':['全部为京东官方同名退款事件金额；申请日、完结日与付款日不能混用。','不同退款阶段保持官方原名，未核验为互斥完备集合，不将缺失补零或强制凑总。','退款事件金额不得直接除以同期成交金额称退货率，也不直接扣减为净销售。','尚未取得真实原因、商品热点和付款队列，不能据汇总金额推断质量、尺码或物流是原因。']}

def markdown(report):
    lines=['','## 售后退款事件分析',f"范围：{report['period']}；状态：partial；退款事件不等于同成交批次退货。",'| 官方指标 | 本期金额 | 前期金额 | 相对变化 |','|---|---:|---:|---:|']
    for name,m in report['metrics'].items():
        fmt=lambda v:'缺失' if v is None else f'{v:,.2f}'
        delta='不可计算' if m['relative_change'] is None else f"{m['relative_change']*100:+.2f}%"
        lines.append(f"| {name} | {fmt(m['current'])} | {fmt(m['previous'])} | {delta} |")
    lines+=['','分项数值核对：'+str(report['component_reconciliation']),*['- '+s for s in report['limitations']],'仍缺：'+'；'.join(report['missing_sources'])]
    cases=report.get('application_day_cases',{})
    if cases.get('status')=='verified':
        lines+=['','## 已核验申请日服务单',f"申请日：{cases['date']}；唯一服务单{cases['unique_service_count']}张；原因已知{cases['reason_known_services']}张、未知{cases['reason_missing_services']}张。",f"状态采集时间：{cases['captured_from']} 至 {cases['captured_to']}；与上方退款事件窗口分开解读。"]
        lines+=['- '+name+'：'+str(count)+'张服务单' for name,count in cases['reason_distribution'].items()]
        lines+=['- 不将申请日原因解释为七日退款事件的完整归因；不计算真实退货率。']
    return '\n'.join(lines)+'\n'

def saved_cases(day,store,*,root=None):
    """Replay local business projections; never acquire more pages implicitly."""
    from .after_sales import parse,aggregate
    root=Path(root) if root is not None else ROOT
    base=root/'data/jd'/store.replace(':','_')/day
    paths=sorted((base/'after-sales-full').glob('*/report.json'))
    if not paths:return {'status':'unavailable','date':day,'time_basis':'application_day'}
    try:
        full=json.loads(paths[-1].read_text(encoding='utf-8'));pages=[];times=[]
        if full.get('store_key')!=store or full.get('date')!=day:raise ValueError('售后缓存店铺或申请日不符')
        for index,filename in enumerate(full['page_reports'],1):
            p=Path(filename).resolve()
            if not p.is_relative_to((base/'after-sales-list').resolve()):raise ValueError('售后分页证据路径超出本店本日')
            r=json.loads(p.read_text(encoding='utf-8'));raw=(p.parent/'response.json').read_text(encoding='utf-8');proof=r['proof']
            if hashlib.sha256(raw.encode()).hexdigest()!=proof['response_sha256'] or proof['identity']['store_key']!=store or proof['identity'].get('merchant_identity_kind')!='official_shop_information' or proof.get('source')!='registered-api' or proof.get('request_mode')!='official-ui-observer-business-projection':raise ValueError('售后分页原文哈希或来源身份不符')
            replay=parse(json.loads(raw),day,index,page_size=100)
            if replay['orders']!=r['orders']:raise ValueError('售后分页记录与原文不符')
            replay['report_path']=str(p);pages.append(replay);times.append(proof['received_at'])
        result=aggregate(pages,day,store)
        if not result['whole_day_complete'] or not full.get('whole_day_complete'):return {'status':'partial','date':day,'time_basis':'application_day','unique_service_count':result['unique_service_count'],'missing_services':result['missing_services'],'errors':result['errors']}
        for key in ['unique_service_count','official_total','reason_distribution','refund_amount_known_sum']:
            if result[key]!=full[key]:raise ValueError('售后整日汇总与原文重放不符')
        return {k:v for k,v in result.items() if k not in ('orders','item_hotspots','page_reports')}|{'status':'verified','captured_from':min(times),'captured_to':max(times),'item_service_hotspots_top10':result['item_hotspots'][:10],'report_path':str(paths[-1])}
    except (OSError,ValueError,KeyError,TypeError) as exc:return {'status':'invalid','date':day,'time_basis':'application_day','error':str(exc)}

def saved_context(day,store,*,root=None):
    from .panorama import load_overview
    root=Path(root) if root is not None else ROOT
    dates=[(date.fromisoformat(day)-timedelta(days=i)).isoformat() for i in range(13,-1,-1)]
    reports=[]
    for d in dates:
        path=root/'data/jd'/store.replace(':','_')/d/'report.json'
        reports.append({**load_overview(path,d,store),'report_path':str(path)})
    report=analyze(reports,day,store,weekly=True)
    cases=saved_cases(day,store,root=root);report['application_day_cases']=cases
    if cases.get('status')=='verified':
        report['limitations'][-1]='已取得目标申请日的完整服务单原因和商品关联，另列application_day_cases；不代表上方七日退款事件的完整归因，原付款队列仍缺失。'
        report['missing_sources']=['其他申请日的全量服务单与同口径对照','原订单付款批次及同批次支付件数/订单数','成熟观察窗及重复服务单/部分退款关系']
    return report

def collect(day,store,*,root=None):
    root=Path(root) if root is not None else ROOT
    report=saved_context(day,store,root=root)
    folder=root/'data/jd'/store.replace(':','_')/day/'refund-review'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder.mkdir(parents=True,exist_ok=False)
    report.update(report_path=str(folder/'report.json'),markdown_path=str(folder/'report.md'))
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (folder/'report.md').write_text('# 京东退货归因 · 退款事件部分\n'+markdown(report),encoding='utf-8')
    return report
