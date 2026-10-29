"""Fixed OneService user statistics, through the existing registered bridge."""
from copy import deepcopy
import json,re,uuid
from pathlib import Path

CONTRACTS=json.loads((Path(__file__).resolve().parents[3]/'extension/unpacked/user-metric-contracts.json').read_text(encoding='utf-8'))
TERMINAL_REPORTS=frozenset('analysis-benefits-comprehensive-products-sku-full-pages'+suffix for suffix in ('','-week','-month','-custom'))

def make_body(report,params):
    from .user_analysis import validate_params
    validate_params(report,params)
    body=deepcopy(CONTRACTS[report]['template'])
    day=params['endDate']
    def replace(value):
        if value=='$PAGE':return params['pageNum']
        if isinstance(value,str):return value.replace('$DAY',day).replace('$START',params['startDate']).replace('$DATE_CODE',params['date']).replace('$PERIOD',CONTRACTS[report].get('period','day')).replace('$INTERVAL',{'week':'BY_WEEK','month':'BY_MONTH'}.get(CONTRACTS[report].get('period'),'BY_DAY')).replace('$SECOND',params.get('secondIndId','')).replace('$THIRD',params.get('thirdIndId','')).replace('$RIGHTS',params.get('rightsType','')).replace('$TRACE',str(uuid.uuid4())).replace('$BATCH',str(uuid.uuid4()))
        if isinstance(value,list):return [replace(v) for v in value]
        if isinstance(value,dict):return {k:replace(v) for k,v in value.items()}
        return value
    return replace(body)

def validate_body(report,params,body):
    if report not in CONTRACTS or not isinstance(body,dict):raise ValueError('未登记会员指标模板。')
    expected=make_body(report,params)
    cp=body.get('commonParam')
    if not isinstance(cp,dict):raise ValueError('缺少会员查询参数。')
    for key in ('traceId','batchId'):
        value=cp.get(key)
        if not isinstance(value,str) or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',value):raise ValueError('会员查询追踪ID无效。')
        expected['commonParam'][key]=value
    if body!=expected:raise ValueError('会员查询超出已登记的固定模板。')
    return body

def business_body(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get('header'),dict) or str(payload['header'].get('code')) not in ('200','2000'):raise ValueError('会员指标业务状态失败。')
    if 'status' in payload and (type(payload['status']) not in (str,int) or str(payload['status'])!='0'):raise ValueError('会员指标网关业务状态失败。')
    errors=payload.get('errors')
    if errors is not None and (not isinstance(errors,list) or any(not isinstance(error,dict) for error in errors)):raise ValueError('会员指标错误字段结构无效。')
    if str(payload['header']['code'])=='200' and errors:raise ValueError('会员指标返回错误。')
    body=payload.get('body')
    if not isinstance(body,dict):raise ValueError('会员指标缺少body。')
    return body

def parse(payload,report,*,contract=None):
    contract=CONTRACTS[report] if contract is None else contract
    body=business_body(payload)
    metadata=body.get('metaData');rows=body.get('data');size=body.get('size')
    row_limit=contract.get('row_limit')
    if str(payload['header']['code'])=='200' and type(size) is int and size==0 and 'data' in body and rows is None and isinstance(metadata,dict) and {'meta','metaIndex'}<=metadata.keys() and metadata['meta'] is None and metadata['metaIndex'] is None:
        return {'data':{'rows':[],'derived_metrics':[],'metric_labels':contract['metric_labels'],'official_total':0},'coverage':{'scope':'fixed_official_user_metric_dataset','nulls_preserved':True,'all_store_catalog_complete':False,'returned_rows':0,'row_limit':row_limit,'whole_query_complete':not contract.get('window_days'),'official_business_code':'200','official_warnings':[],'missing_metrics':[],'official_empty':True,'note':'官方成功且size=0/data=null的空结果；不生成任何零值指标。'}}
    if not isinstance(metadata,dict) or not isinstance(rows,list) or type(size) is not int or not 0<=size<=100000000 or len(rows)>size or len(rows)>(row_limit or 2000) or not row_limit and size!=len(rows):raise ValueError('会员指标结构或返回总数不完整。')
    indices=metadata.get('metaIndex')
    required=contract['template']['metricList']+contract['template']['groupList']
    warning=str(payload['header']['code'])=='2000'
    if not isinstance(indices,dict) or not indices or any(not isinstance(f,str) or type(i) is not int or i< -1 for f,i in indices.items()):raise ValueError('会员指标索引缺失或无效。')
    missing=[f for f in required if f not in indices or indices[f]<0]
    if missing and not warning:raise ValueError('会员指标列缺失。')
    width=max(indices.values())+1
    if any(not isinstance(row,list) or len(row)!=width for row in rows):raise ValueError('会员指标行列宽度不符。')
    output=[{f:row[i] for f,i in indices.items() if i>=0} for row in rows]
    coverage={'scope':'fixed_official_user_metric_dataset','nulls_preserved':True,'all_store_catalog_complete':False,'returned_rows':len(rows),'row_limit':row_limit,'whole_query_complete':not warning and size==len(rows),'official_business_code':str(payload['header']['code']),'official_warnings':deepcopy(payload.get('errors') or []),'missing_metrics':missing,'note':'固定官方指标集合；2000是官方部分指标警告，保留原始错误及缺失列，不能当完整成功。商品表有登记行数上限，不代表页面全部统计或全店商品全集。缺失分子/分母不补零。'}
    groups=contract['template']['groupList']
    coverage['group_dimensions']=groups
    if contract.get('indexation'):coverage.update(indexation=True,note=coverage['note']+' 行业榜单原始指标可能为指数区间对象，保留原文，不取中点、不当精确人数或金额；仅官方Top10范围。')
    for field in ('sku_id','spu_id'):
        if field in groups:coverage['unique_'+field.removesuffix('_id')+'s_returned']=len({row[field] for row in output if row.get(field) is not None})
    if 'jdr_sch_plus__rights_type' in groups and row_limit:
        coverage['group_rows_may_overlap']=True
        coverage['note']+=' 同一商品可能出现在多种权益下，权益分组行不能直接相加作为唯一商品或去重人数。'
    coverage['warning_metrics']=sorted({f for error in payload.get('errors') or [] for f in (error.get('indicators') if isinstance(error.get('indicators'),list) else []) if isinstance(f,str)})
    if contract.get('window_days'):
        times=[]
        for row in output:
            value=row.get('dt')
            if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError('会员/权益趋势日期字段无效。')
            from datetime import date
            times.append(date.fromisoformat(value))
        coverage.update(returned_start=min(times).isoformat() if times else None,returned_end=max(times).isoformat() if times else None,unique_dates=len(set(times)),duplicate_dates=len(times)-len(set(times)),missing_days_within_span=(max(times)-min(times)).days+1-len(set(times)) if times else None)
        expected_days=contract['window_days']
        coverage.update(expected_window_days=expected_days,missing_days_in_requested_window=max(0,expected_days-len(set(times))))
        group_fields=contract.get('trend_groups')
        if group_fields:
            series={tuple(row.get(f) for f in group_fields) for row in output}
            expected_series={('NEW',),('OLD',)} if report=='analysis-member-overview-newold-trend' else series
            details=[]
            for group in sorted(expected_series):
                days=[day for row,day in zip(output,times) if tuple(row.get(f) for f in group_fields)==group]
                complete=len(days)==len(set(days))==expected_days and (max(days)-min(days)).days+1==expected_days
                details.append({'group':list(group),'returned_rows':len(days),'unique_dates':len(set(days)),'complete':complete})
            coverage.update(series_coverage=details,duplicate_dates=sum(s['returned_rows']-s['unique_dates'] for s in details))
            coverage['whole_query_complete']=coverage['whole_query_complete'] and series==expected_series and all(s['complete'] for s in details)
        else:coverage['whole_query_complete']=coverage['whole_query_complete'] and len(set(times))==expected_days and len(times)==expected_days and coverage['missing_days_within_span']==0
    return {'data':{'rows':output,'derived_metrics':[derived_metrics(row,report) if report in CONTRACTS else {} for row in output],'metric_labels':contract['metric_labels'],'official_total':size},'coverage':coverage}

def derived_metrics(row,report):
    """Page formulas, with raw inputs separate and unknown denominators retained."""
    labels=CONTRACTS[report]['metric_labels'];codes={v:k for k,v in labels.items()}
    if report not in ('analysis-member-overview-summary','analysis-member-overview-card','analysis-member-overview-operable'):return {}
    if report.endswith('-operable'):
        formulas=[('可运营开卡会员占比','可运营开卡会员数','在运营会员总数'),('沉默开卡会员占比','沉默开卡会员数','在运营会员总数'),*[(name+'占比',name+'数','可运营开卡会员数') for name in ('高价值开卡会员','活跃开卡会员','潜力开卡会员')]]
    else:
        card=report.endswith('-card')
        formulas=[('会员成交客单价','会员成交金额','会员成交客户数'),('会员成交转化率','会员成交客户数','会员进店访客数'),('会员30天复购率','30日复购会员数' if card else '会员30日复购用户数','30日成交客户数' if card else '会员30日成交客户数'),('会员90天复购率','90日复购会员数' if card else '会员90日复购用户数','90日成交客户数' if card else '会员90日成交客户数')]
    result={}
    for name,num,den in formulas:
        n=row.get(codes[num]);d=row.get(codes[den])
        value=n/d if type(n) in (int,float) and type(d) in (int,float) and d>0 else None
        result[name]={'value':value,'numerator':n,'denominator':d,'numerator_metric':codes[num],'denominator_metric':codes[den],'source':'calculated_from_official_metrics'}
    return result

def pagination_progress(results,*,require_complete=False,mode=None):
    if mode=='list_total_v1':
        from .user_options import list_progress
        return list_progress(results,require_complete)
    if mode=='terminal_v1':return terminal_pagination_progress(results,require_complete=require_complete)
    if mode is not None:raise ValueError('未登记分页核验模式。')
    if not results:raise ValueError('缺少分页结果。')
    report=results[0]['section'];contract=CONTRACTS.get(report,{})
    pagination=contract.get('pagination')
    if not pagination:raise ValueError('该指标表未登记分页。')
    page_size=pagination['page_size'];seen=set();total=None;count=0
    for page,item in enumerate(results,1):
        if item['section']!=report or type(item['params'].get('pageNum')) is not int or item['params']['pageNum']!=page:raise ValueError('分页缺页、乱序或混入其他表。')
        data=item['result']['data'];current=data['official_total'];rows=data['rows']
        if type(current) is not int or current<0 or total is not None and current!=total:raise ValueError('分页官方总数发生变化。')
        total=current
        expected=max(0,min(page_size,total-(page-1)*page_size))
        if len(rows)!=expected or page>max(1,(total+page_size-1)//page_size):raise ValueError('分页行数不足、超额或越过末页。')
        for row in rows:
            key=tuple(row.get(f) for f in pagination['group_key'])
            if any(not isinstance(v,str) or not re.fullmatch(r'\d+',v) for v in key) or key in seen:raise ValueError('分页分组键缺失或重复，不能认定全量。')
            seen.add(key)
        count+=len(rows)
    complete=count==total and len(seen)==total
    if require_complete and not complete:raise ValueError('分页未取全。')
    return {'complete':complete,'official_total':total,'captured_groups':count,'unique_groups':len(seen),'missing_groups':total-len(seen),'pages':len(results),'page_size':page_size,'group_key':pagination['group_key'],'note':'以SKU与权益类型组合核验分组完整；不等同唯一SKU数，也不跨权益加总去重人数。'}


def verify_pagination(results,*,mode=None):return pagination_progress(results,require_complete=True,mode=mode)


def terminal_page_result(result):
    """Expose the page-level size without calling it the whole-period total."""
    data=dict(result['data']);size=data.pop('official_total');data['official_size']=size
    coverage={**result['coverage'],'size_semantics':'page_disclosure_hint_until_terminal','whole_query_complete':False,
        'note':result['coverage'].get('note','')+' 当前页size不是固定区间总数；全量状态以pagination_verification为准。空页不表示整个区间无数据。'}
    return {**result,'data':data,'coverage':coverage}


def terminal_pagination_progress(results,*,require_complete=False):
    if not results or len(results)>1000:raise ValueError('缺少分页结果或超过1000页上限。')
    report=results[0]['section']
    if report not in TERMINAL_REPORTS:raise ValueError('该指标表未核验动态size与官方空页语义。')
    contract=CONTRACTS[report];size=contract['pagination']['page_size'];group_fields=contract['pagination']['group_key']
    scope={k:v for k,v in results[0]['params'].items() if k!='pageNum'}
    seen=set();skus=set();count=0;history=[];last_hint=0;short_page=None;short_total=None;eof=None
    for page,item in enumerate(results,1):
        params=item['params'];data=item['result']['data'];coverage=item['result']['coverage']
        if item['section']!=report or type(params.get('pageNum')) is not int or params['pageNum']!=page or {k:v for k,v in params.items() if k!='pageNum'}!=scope:raise ValueError('分页缺页、乱序或查询范围不一致。')
        if eof is not None:raise ValueError('官方空页之后不允许继续拼接数据。')
        current=data.get('official_size',data.get('official_total'));rows=data['rows'];n=len(rows)
        if type(current) is not int or current<0 or n>size:raise ValueError('分页size或行数无效。')
        history.append(current)
        if not n:
            if current!=0 or not coverage.get('official_empty') or coverage.get('official_business_code')!='200':raise ValueError('末页必须为明确的官方成功空页。')
            if count<last_hint:raise ValueError('提前空页，与已返回size提示不符。')
            eof=page;continue
        if short_page is not None:raise ValueError('不足整页之后仍有数据，末页证据冲突。')
        if current<count+n or current<last_hint:raise ValueError('分页size小于已取数量或异常回退。')
        for row in rows:
            key=tuple(row.get(f) for f in group_fields)
            if any(not isinstance(v,str) or not re.fullmatch(r'\d+',v) for v in key) or key in seen:raise ValueError('分页分组键缺失或重复，不能认定全量。')
            seen.add(key);skus.add(row['sku_id'])
        count+=n;last_hint=current
        if n<size:
            if current!=count:raise ValueError('不足整页的size与累计唯一分组数不符。')
            short_page=page;short_total=current
    complete=eof is not None
    if require_complete and not complete:raise ValueError('尚未取得官方成功空页，不能认定全量。')
    return {'complete':complete,'official_total':short_total if complete else None,'captured_groups':count,'unique_groups':len(seen),'unique_skus':len(skus),
        'missing_groups':0 if complete else None,'pages':len(results),'data_pages':len(results)-(1 if eof else 0),'page_size':size,'group_key':group_fields,
        'size_semantics':'page_disclosure_hint_until_terminal','size_history':history,'last_nonempty_page':len(results)-(1 if eof else 0) if count else None,
        'short_page':short_page,'terminal_empty_page':eof,'total_source':'short_page_size_confirmed_by_empty_page' if complete and short_total is not None else 'contiguous_unique_groups_confirmed_by_empty_page' if complete else 'not_confirmed',
        'note':'满页size不作固定全区间总数；连续页、唯一SKU与权益组合、不足整页计数(如有)及后续官方成功空页共同核验。恰好整页时总数按完整读取行数计算，不冒充官方精确总数。权益分组不等于唯一SKU数，不跨权益加总去重人数。'}
