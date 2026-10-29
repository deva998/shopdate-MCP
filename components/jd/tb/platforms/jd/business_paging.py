"""Bounded official gift-activity pagination, retaining each original receipt."""
import json
from datetime import datetime


def combine_pages(pages,recheck):
    if not pages or not isinstance(pages[0],dict):raise ValueError('礼金缺少第一页。')
    first=pages[0]
    fields=('pageSize','pageCount','totalCount')
    if any(type(first.get(k)) is not int or first[k]<0 for k in fields) or first['pageSize']<1 or first['pageCount']>2000:raise ValueError('礼金分页计数无效。')
    total=first['totalCount'];size=first['pageSize'];count=max(1,first['pageCount'])
    if first['pageCount']!=(total+size-1)//size or len(pages)!=count:raise ValueError('礼金页数与官方总数不符。')
    first_ids=[r.get('activityId') if isinstance(r,dict) else None for r in first.get('list',[])]
    if not isinstance(recheck,dict) or any(type(recheck.get(k)) is not int or recheck[k]!=first[k] for k in fields) or type(recheck.get('pageNumber')) is not int or recheck['pageNumber']!=1 or not isinstance(recheck.get('list'),list) or [r.get('activityId') if isinstance(r,dict) else None for r in recheck['list']]!=first_ids:raise ValueError('礼金末尾复查首页活动或总数变化，不能宣称全量。')
    rows=[]
    for i,page in enumerate(pages,1):
        if not isinstance(page,dict) or any(type(page.get(k)) is not int or page[k]!=first[k] for k in fields) or type(page.get('pageNumber')) is not int or page['pageNumber']!=i or not isinstance(page.get('list'),list) or len(page['list'])!=max(0,min(size,total-(i-1)*size)):raise ValueError('礼金分页缺页、重复页或总数变化。')
        rows.extend(page['list'])
    ids=[r.get('activityId') if isinstance(r,dict) else None for r in rows]
    if any(not isinstance(x,str) or not x.isdigit() for x in ids) or len(set(ids))!=len(ids) or len(ids)!=total:raise ValueError('礼金活动ID重复、缺失或数量不符。')
    return {'data':{'activities':rows},'coverage':{'pagination_complete':True,'official_total':total,
        'unique_activities':len(set(ids)),'returned_rows':len(rows),'verified_pages':count,
        'page_size':size,'first_page_rechecked':True,'scope':'current_activity_list','atomic_snapshot':False,
        'whole_module_complete':False,'schema_validation':'live_observed_structure_verified',
        'nulls_preserved':True,'note':'当前活动列表全量分页，分多次读取，不是原子快照；不按归档日期筛选，也不代表单日销售或全模块接入完成。'}}


def collect_remaining(client,day,first,folder):
    from .business_stats import params,business_body
    from shopdate_workflows.evidence import write_evidence
    write_evidence(folder/'pagination-pages/page-0001.json',
        {'platform':'jd','store_key':client.identity['store_key'],'date':day,**first})
    body=business_body(json.loads(first['response_text']),'gift-money-activities')
    count=body.get('pageCount')
    if type(count) is not int or not 0<=count<=2000:raise ValueError('礼金分页数无效或超出读取上限。')
    entries=[]
    for page in [*range(2,count+1),1]:
        values=params('gift-money-activities',day,page=page)
        raw,proof=client.request('business-stats',day,scope={'report':'gift-money-activities','params':values})
        entry={'params':values,'response_text':client.last_response_text,'proof':proof,'recheck':page==1}
        business_body(raw,'gift-money-activities')
        write_evidence(folder/'pagination-pages'/('recheck.json' if page==1 else f'page-{page:04}.json'),
            {'platform':'jd','store_key':client.identity['store_key'],'date':day,**entry})
        entries.append(entry)
    return entries


def verify_saved(payload,day,store):
    from .business_stats import params,verify_proof,business_body
    entries=payload.get('pagination_evidence')
    if not isinstance(entries,list) or not entries:raise ValueError('礼金全量缺少分页和末尾复查证据。')
    pages=[business_body(json.loads(payload['response_text']),'gift-money-activities')];recheck=None
    previous=datetime.fromisoformat(payload['proof']['request_started_at'].replace('Z','+00:00'))
    for i,entry in enumerate(entries):
        last=i==len(entries)-1
        if not isinstance(entry,dict) or entry.get('recheck')!=last:raise ValueError('礼金复查证据顺序无效。')
        values=params('gift-money-activities',day,page=1 if last else i+2)
        if entry.get('params')!=values:raise ValueError('礼金分页证据参数不符。')
        verify_proof(entry['proof'],'gift-money-activities',values,day,store,entry['response_text'])
        at=datetime.fromisoformat(entry['proof']['request_started_at'].replace('Z','+00:00'))
        if at<=previous:raise ValueError('礼金分页或末尾复查的采集时间未严格递增。')
        previous=at
        body=business_body(json.loads(entry['response_text']),'gift-money-activities')
        if last:recheck=body
        else:pages.append(body)
    return combine_pages(pages,recheck)
