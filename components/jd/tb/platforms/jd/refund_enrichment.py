"""Exact original-order linkage and right-censored 30-day observations."""
from collections import Counter
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
import hashlib,json,re
from .api_client import ROOT
from . import orders

CHINA=timezone(timedelta(hours=8))

class PaymentConflictError(ValueError):
    """Two verified sources disagree: stop instead of choosing a maturity date."""

def make_lookup_body(end_day,identifiers):
    end=date.fromisoformat(end_day)
    if end.isoformat()!=end_day or not isinstance(identifiers,list) or not 1<=len(identifiers)<=50 or len(set(identifiers))!=len(identifiers) or any(not isinstance(i,str) or not re.fullmatch(r'[1-9]\d{0,19}',i) for i in identifiers):raise ValueError('原订单查询编号范围无效')
    body=orders.make_body(end_day)
    body['request']['data'].update(orderIds=identifiers,orderCreateTimeBegin=(end-timedelta(days=179)).isoformat()+' 00:00:00')
    return body

def parse_lookup(payload,end_day,identifiers,merchant_id,*,merchant_binding=None):
    body=make_lookup_body(end_day,identifiers);data=payload.get('data',{});raw=data.get('results')
    totals=[v for v in (data.get('total'),data.get('totalItem')) if v is not None]
    if not isinstance(raw,list) or len(raw)>50 or not totals or any(type(v) is not int or v<0 or v>len(identifiers) for v in totals) or len(set(totals))!=1 or totals[0]!=len(raw):raise ValueError('原订单精确查询总数或记录不符')
    found={};begin=body['request']['data']['orderCreateTimeBegin'][:10]
    # Reuse the existing strict per-record business whitelist and merchant checks.
    if not raw:orders.parse(payload,end_day,1,merchant_id,merchant_binding=merchant_binding,page_size=50)
    for row in raw:
        created=orders._time(row.get('orderCreateTime'))
        if not created or not begin<=created[:10]<=end_day:raise ValueError('原订单超出已核验查询时间范围')
        one={**payload,'data':{**data,'total':1,'totalItem':1,'results':[row]}}
        parsed=orders.parse(one,created[:10],1,merchant_id,merchant_binding=merchant_binding,page_size=50)['orders'][0]
        identifier=parsed['order_id']
        if identifier not in identifiers or identifier in found:raise ValueError('原订单返回未请求编号或重复，停止关联')
        found[identifier]=parsed
    return {'orders':list(found.values()),'requested_order_ids':identifiers,'missing_order_ids':[i for i in identifiers if i not in found],
        'end_day':end_day,'time_basis':'exact_order_ids_within_180_created_days','not_complete_payment_cohort':True}

def timestamp(value):
    stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
    return stamp.replace(tzinfo=CHINA) if stamp.tzinfo is None else stamp.astimezone(CHINA)

def analyze(cases,index,as_of):
    now=timestamp(as_of);rows=cases['orders'];ids={r['order_id'] for r in rows if r.get('order_id')}
    known=[r for r in rows if r.get('refund_fields',{}).get('refundAmount') is not None]
    unknown=[r for r in rows if r.get('refund_fields',{}).get('refundAmount') is None]
    success=[r for r in rows if r.get('refund_fields',{}).get('refundStatusName')=='退款成功']
    applied=[r for r in unknown if r.get('refund_fields',{}).get('applyRefundAmount') is not None]
    maturity={};cohorts=Counter();mature=immature=invalid=missing_time=0
    for identifier in sorted(ids&index.keys()):
        raw=index[identifier].get('payment_confirmed_at')
        if not raw:missing_time+=1;maturity[identifier]={'status':'payment_time_unknown'};continue
        try:paid=timestamp(raw)
        except (TypeError,ValueError):missing_time+=1;maturity[identifier]={'status':'payment_time_invalid'};continue
        if paid>now:invalid+=1;maturity[identifier]={'status':'future_payment_time_invalid'};continue
        due=paid+timedelta(days=30);state='mature' if now>=due else 'immature'
        if state=='mature':mature+=1
        else:immature+=1
        cohorts[paid.date().isoformat()]+=1
        maturity[identifier]={'status':state,'payment_confirmed_at':paid.isoformat(),'observation_due_at':due.isoformat(),'elapsed_days':round((now-paid).total_seconds()/86400,4)}
    return {'platform':cases['platform'],'store_key':cases['store_key'],'date':cases['date'],'status':'partial','as_of':now.isoformat(),
        'source_service_count':len(rows),'source_service_day_complete':cases['whole_day_complete'],
        'amount_coverage':{'actual_amount_known_services':len(known),'actual_amount_unknown_services':len(unknown),
            'application_amount_only_services':len(applied),'application_amount_only_known_sum':float(sum((Decimal(str(r['refund_fields']['applyRefundAmount'])) for r in applied),Decimal(0))),
            'successful_refund_services':len(success),'successful_refund_amount_known_services':sum(r['refund_fields'].get('refundAmount') is not None for r in success),
            'unknown_amount_service_states':dict(Counter(r.get('status_fields',{}).get('afsServiceStatusName') or '未知' for r in unknown)),
            'unknown_amount_policy':'官方未返回实际退款金额；申请金额不替代实际金额，不补零。'},
        'payment_linkage':{'requested_unique_orders':len(ids),'linked_unique_orders':len(ids&index.keys()),'unmatched_unique_orders':len(ids-index.keys()),
            'linked_services':sum(r.get('order_id') in index for r in rows),'payment_time_known_unique_orders':mature+immature,
            'linked_order_payment_day_counts':dict(cohorts),'scope':'only_original_orders_referenced_by_this_application_day'},
        'observation':{'days':30,'mature_unique_orders':mature,'immature_unique_orders':immature,'unknown_payment_time_orders':missing_time,
            'invalid_future_payment_orders':invalid,'complete_payment_cohort_denominator':False,'calendar_maturity_only':True,'outcome_window_complete':False,'observed_service_dates':[cases['date']],'policy':'30 elapsed days after payment confirmation, immature orders are right-censored'},
        'order_observations':maturity,'cohort_return_rate':None,
        'limitations':['关联售后原订单不是完整付款日队列，不能以发生售后的订单作分母。','退款状态为采集时快照；30天是用户选定分析观察期，不等同官方售后期限。','未关联、缺付款时间、未来付款时间和未成熟订单分别计数；不当作未退货。','日龄满30天只代表日历成熟；当前仅含一个申请日服务单，不代表已覆盖该订单全部30天售后结果。','原始父拆单关系及完整付款队列/后续售后观察未齐，不输出真实退货率。']}

def load_cases(day,store):
    from .refund_review import saved_cases
    from .after_sales import parse,aggregate
    verified=saved_cases(day,store)
    if verified.get('status')!='verified':raise ValueError('补齐需先有完整且重放通过的本店本日售后服务单')
    full=json.loads(Path(verified['report_path']).read_text(encoding='utf-8'));pages=[]
    for n,name in enumerate(full['page_reports'],1):
        p=Path(name);r=json.loads(p.read_text(encoding='utf-8'));part=parse(json.loads((p.parent/'response.json').read_text(encoding='utf-8')),day,n,page_size=100);part['report_path']=str(p);pages.append(part)
    result=aggregate(pages,day,store)
    if not result['whole_day_complete']:raise ValueError('售后服务单全量重放失败')
    return result,verified['report_path']

def saved_order_index(store):
    from .order_review import latest_verified
    index={};sources=[];errors=[]
    for folder in sorted((ROOT/'data/jd'/store.replace(':','_')).glob('????-??-??')):
        if not (folder/'order-list').is_dir():continue
        try:report=latest_verified(folder.name,store)
        except (OSError,ValueError,KeyError,TypeError) as exc:errors.append({'date':folder.name,'error':str(exc)});continue
        for row in report['orders']:
            prior=index.get(row['order_id'])
            if prior and prior.get('payment_confirmed_at')!=row.get('payment_confirmed_at'):raise ValueError('同订单原付款时刻在已核验记录中冲突')
            index[row['order_id']]=row
        sources.append(report['report_path'])
    return index,sources,errors

def saved_lookup_index(store,*,include_missing=False):
    index={};sources=[];errors=[];seen=set();missing={};base=(ROOT/'data/jd'/store.replace(':','_')).resolve()
    paths=sorted(set(base.glob('????-??-??/refund-enrich/*/report.json'))|set(base.glob('????-??-??/refund-enrich/*/checkpoint.json')))
    for path in paths:
        try:
            report=json.loads(path.read_text(encoding='utf-8'))
            if report.get('platform')!='jd' or report.get('store_key')!=store:raise ValueError('原付款缓存店铺不符')
            for batch in report.get('lookup_proofs',[]):
                p=Path(batch['response_path']).resolve()
                if p in seen:continue
                if not p.is_relative_to(base):raise ValueError('原付款缓存正文超出本店路径')
                proof=batch['proof'];identity=proof['identity'];ids=batch['requested_order_ids'];day=proof['date'];raw=p.read_text(encoding='utf-8')
                if proof.get('case')!='order-lookup' or proof.get('source')!='registered-api' or identity.get('store_key')!=store or identity.get('merchant_identity_kind')!='official_shop_information' or proof.get('request_body')!=make_lookup_body(day,ids) or hashlib.sha256(raw.encode()).hexdigest()!=proof.get('response_sha256'):raise ValueError('原付款缓存哈希、查询编号或身份不符')
                part=parse_lookup(json.loads(raw),day,ids,identity['merchant_id'],merchant_binding=identity.get('merchant_binding'))
                if include_missing and proof.get('received_at'):
                    try:
                        age=(datetime.now(CHINA)-timestamp(proof['received_at'])).total_seconds()
                        if 0<=age<=900 and day==datetime.now(CHINA).date().isoformat():
                            for identifier in part['missing_order_ids']:missing[identifier]={'received_at':proof['received_at'],'response_path':str(p),'scope':'not_returned_in_verified_exact_id_query_within_180_created_days'}
                    except (ValueError,TypeError):pass
                for row in part['orders']:
                    prior=index.get(row['order_id'])
                    if prior and prior.get('payment_confirmed_at') and row.get('payment_confirmed_at') and timestamp(prior['payment_confirmed_at'])!=timestamp(row['payment_confirmed_at']):raise PaymentConflictError('原付款缓存时间冲突，停止成熟度分析')
                    if not prior or row.get('payment_confirmed_at'):index[row['order_id']]=row
                seen.add(p);sources.append(str(p))
        except PaymentConflictError:raise
        except (OSError,ValueError,TypeError,KeyError) as exc:errors.append({'path':str(path),'error':str(exc)})
    return (index,sources,errors,missing) if include_missing else (index,sources,errors)

def collect(day,store):
    from .api_client import APIClient
    cases,case_source=load_cases(day,store);index,sources,errors=saved_order_index(store)
    cached,cached_sources,cached_errors,missing_evidence=saved_lookup_index(store,include_missing=True);sources+=cached_sources;errors+=cached_errors
    for identifier,row in cached.items():
        prior=index.get(identifier)
        if prior and prior.get('payment_confirmed_at') and row.get('payment_confirmed_at') and timestamp(prior['payment_confirmed_at'])!=timestamp(row['payment_confirmed_at']):raise ValueError('原订单与缓存付款时刻冲突')
        if not prior or not prior.get('payment_confirmed_at') or row.get('parent_relation_status'):index[identifier]=row
    today=datetime.now(CHINA).date().isoformat();targets={r['order_id'] for r in cases['orders'] if r.get('order_id')}
    related=set(targets);todo=list(targets)
    while todo:
        parent=index.get(todo.pop(),{}).get('parent_order_id')
        if parent and parent not in related:related.add(parent);todo.append(parent)
    reused_missing={i for i in related if i not in targets and i not in index and i in missing_evidence}
    pending=sorted(i for i in related if i not in reused_missing and (i not in index or not index[i].get('payment_confirmed_at') or not index[i].get('parent_relation_status')))
    folder=ROOT/'data/jd'/store.replace(':','_')/day/'refund-enrich'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');folder.mkdir(parents=True,exist_ok=False)
    proofs=[]
    if pending:
        try:
            with APIClient({'platform':'jd','store_key':store},min_extension='0.9.15') as client:
                attempted=set();batch=0
                while pending:
                    ids=pending[:50];pending=pending[50:];attempted.update(ids);batch+=1
                    if len(attempted)>5000:raise ValueError('原订单及父单读取超过5000个安全预算；保留部分结果')
                    print(f'原付款补齐：批次{batch}，查询{len(ids)}个唯一订单',flush=True)
                    payload,proof=client.request('order-lookup',today,scope={'order_ids':ids})
                    parsed=parse_lookup(payload,today,ids,proof['identity']['merchant_id'],merchant_binding=proof['identity'].get('merchant_binding'))
                    for incoming in parsed['orders']:
                        previous=index.get(incoming['order_id'])
                        if previous and previous.get('payment_confirmed_at') and incoming.get('payment_confirmed_at') and timestamp(previous['payment_confirmed_at'])!=timestamp(incoming['payment_confirmed_at']):raise PaymentConflictError('新读取父单关系的原付款时间与已核验来源冲突，停止成熟度分析')
                    raw=client.last_response_text
                    if hashlib.sha256(raw.encode()).hexdigest()!=proof['response_sha256']:raise ValueError('原付款查询原文哈希不符')
                    raw_path=folder/f'batch-{batch:04d}-business.json';raw_path.write_text(raw,encoding='utf-8')
                    proofs.append({'proof':proof,'requested_order_ids':ids,'response_path':str(raw_path),'missing_order_ids':parsed['missing_order_ids']})
                    index.update({r['order_id']:r for r in parsed['orders']})
                    for row in parsed['orders']:
                        parent=row.get('parent_order_id')
                        if parent and parent not in attempted and parent not in pending and (parent not in index or not index[parent].get('parent_relation_status')):
                            if parent not in targets and parent not in index and parent in missing_evidence:reused_missing.add(parent)
                            else:pending.append(parent)
                    from .api_products import write_json
                    write_json(folder/'checkpoint.json',{'platform':'jd','store_key':store,'date':day,'lookup_proofs':proofs})
        except PaymentConflictError:raise
        except Exception as exc:errors.append({'error':str(exc)})
    report=analyze(cases,index,datetime.now(CHINA).isoformat())
    from .refund_cohort import relationships
    # Include only this application's original-order graph plus explicitly
    # referenced parents, never label all cached records the payment cohort.
    needed={r['order_id'] for r in cases['orders'] if r.get('order_id')};todo=list(needed)
    while todo:
        parent=index.get(todo.pop(),{}).get('parent_order_id')
        if parent and parent not in needed:needed.add(parent);todo.append(parent)
    report['order_relationships']=relationships({i:index[i] for i in needed if i in index})
    report['order_relationships'].pop('family_by_order',None)
    report['parent_lookup_cache']={'ttl_seconds':900,'reused_unreturned_parent_ids':len(reused_missing),'policy':'只复用当日、近15分钟、哈希/身份/精确编号范围重放通过的未返回父编号；不作为完整关系，不用于原订单付款缺口。'}
    report.update(case_source=case_source,saved_order_sources=sources,lookup_proofs=proofs,errors=errors,report_path=str(folder/'report.json'),markdown_path=str(folder/'report.md'))
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    text=f"# 京东售后原付款关联与30天观察期 {day}\n\n状态：partial；不等同完整付款队列。\n\n金额覆盖：{report['amount_coverage']}\n\n原付款关联：{report['payment_linkage']}\n\n观察期：{report['observation']}\n\n"+'\n'.join('- '+x for x in report['limitations'])
    (folder/'report.md').write_text(text,encoding='utf-8')
    return {k:v for k,v in report.items() if k not in ('order_observations','lookup_proofs')}
