"""Official application-day service cases; no operation or buyer identity fields."""
from collections import Counter
from contextlib import nullcontext
from decimal import Decimal,InvalidOperation
from datetime import date,datetime,timezone,timedelta
from pathlib import Path
import hashlib,json,re
from .api_client import ROOT

PAGE='https://shop.jd.com/jdm/trade/after-sale/independent-after-sale/list?tabCode=all'
URL='https://sff.jd.com/api?v=1.0&appId=BHPQ4MHJBUOQZKTFTRNS&api=dsm.seller.afs.bff.serviceOrderQueryDsmService.page'

def parse(payload,day,page,*,page_size=10):
    if type(page_size) is not int or page_size not in (10,100):raise ValueError('售后每页数量不符')
    q=payload.get('query',{})
    if payload.get('projection')!='jd-afs-business-v1' or payload.get('code')!=200 or any(q.get(k)!=v for k,v in {'date':day,'page':page,'pageSize':page_size,'time_basis':'application_day','tab':'all'}.items()):raise ValueError('售后投影或申请日/分页口径不符')
    begin=int(datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=8))).timestamp()*1000)
    if q.get('dateBegin')!=begin or q.get('dateEnd')!=begin+86400000-1000:raise ValueError('售后原生请求起止时刻不符')
    data=payload.get('data',{});raw=data.get('content');total=data.get('totalNum')
    if not isinstance(raw,list) or type(total) is not int or total<0 or len(raw)>page_size or len(raw)>total:raise ValueError('售后分页记录结构不符')
    rows=[];seen=set();reasons=Counter()
    for row in raw:
        if set(row)-{'afsServiceId','reverseId','reverseType','orderId','customerExpectation','customerExpectationName','serviceOrderBaseFacetDTO','orderFacetDTO','serviceOrderStatusFacetDTO','refundFacetDTO','mainWareFacetDTO','wareFacetDTOList','applyReasonFacetDTO','schema'}:raise ValueError('售后投影包含未登记字段')
        identifier=str(row.get('afsServiceId',''))
        if not re.fullmatch(r'[1-9]\d{0,19}',identifier) or identifier in seen:raise ValueError('售后服务单重复或编号无效')
        seen.add(identifier);labels=row.get('applyReasonFacetDTO',{}).get('afsReasons')
        if labels is not None and (not isinstance(labels,list) or any(not isinstance(s,str) for s in labels)):raise ValueError('售后原因结构不符')
        for label in labels or []:reasons[label]+=1
        base=row.get('serviceOrderBaseFacetDTO',{});refund=row.get('refundFacetDTO',{})
        applied=base.get('afsApplyTime');china=timezone(timedelta(hours=8))
        if type(applied) is int:
            try:stamp=datetime.fromtimestamp(applied/1000,china)
            except (OSError,ValueError,OverflowError):raise ValueError('售后申请时间戳无效') from None
        elif isinstance(applied,str):
            try:stamp=datetime.fromisoformat(applied.replace('Z','+00:00'))
            except ValueError:raise ValueError('售后申请时间格式未核验') from None
            if stamp.tzinfo:stamp=stamp.astimezone(china)
        else:raise ValueError('售后申请时间缺失或类型未核验')
        if stamp.date().isoformat()!=day:raise ValueError('售后记录申请日与本次查询不符')
        items=row.get('wareFacetDTOList') or ([row['mainWareFacetDTO']] if row.get('mainWareFacetDTO') else [])
        rows.append({'service_id':identifier,'order_id':str(row.get('orderId') or row.get('orderFacetDTO',{}).get('orderId') or '') or None,
            'application_time_raw':base.get('afsApplyTime'),'service_type_raw':row.get('reverseType'),
            'status_fields':row.get('serviceOrderStatusFacetDTO',{}),'refund_fields':refund,
            'reasons':labels,'items':items,'original_payment_time_raw':row.get('orderFacetDTO',{}).get('orderPayTime',row.get('orderFacetDTO',{}).get('payTime'))})
    expected=max(0,min(page_size,total-(page-1)*page_size))
    return {'status':'partial','time_basis':'application_day','date':day,'page':page,'page_size':page_size,
        'official_total':total,'observed_records':len(rows),'page_records_complete':len(rows)==expected,
        'whole_day_complete':page==1 and len(rows)==total,'reason_distribution':dict(reasons),
        'orders':rows,'cohort_return_rate':None,'schema':raw[0].get('schema',{}) if raw else {},
        'limitations':['按售后申请日筛选，非当日完结退款或原付款批次；不与商智完结事件直接对账。','仅为当前页服务单；未完成全日唯一服务单核验前不称全日原因占比或热点。','申请退款金额和退款成功金额分开保留；退款状态是采集时快照。','原因按官方真实返回类别计出现次数；服务单、订单和件数的分母不同。','付款队列分母、原始拆单关系及观察期未齐，不生成真实退货率或利润结论。']}

def collect(day,store,page=1,*,page_size=10,client=None):
    from .api_client import APIClient
    if date.fromisoformat(day).isoformat()!=day or not re.fullmatch(r'jd:mall:\d+',store) or type(page) is not int or not 1<=page<=2000:raise ValueError('售后日期、店铺或分页不符')
    with (nullcontext(client) if client else APIClient({'platform':'jd','store_key':store},min_extension='0.9.13')) as client:
        payload,proof=client.request('after-sales-list',day,scope={'page':page,'page_size':page_size})
        raw=client.last_response_text
        report=parse(payload,day,page,page_size=page_size)
    if hashlib.sha256(raw.encode()).hexdigest()!=proof['response_sha256']:raise ValueError('售后业务原文哈希不符')
    folder=ROOT/'data/jd'/store.replace(':','_')/day/'after-sales-list'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');folder.mkdir(parents=True,exist_ok=False)
    (folder/'response.json').write_text(raw,encoding='utf-8')
    report.update(platform='jd',store_key=store,date=day,proof=proof,report_path=str(folder/'report.json'))
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return report

def aggregate(pages,day,store,error=None):
    rows=[];seen=set();issues=[];total=pages[0]['official_total'] if pages else None
    size=pages[0]['page_size'] if pages else 100
    for expected_page,p in enumerate(pages,1):
        if p.get('date')!=day or p.get('page')!=expected_page or p.get('page_size')!=size or p.get('official_total')!=total or not p.get('page_records_complete'):
            issues.append('分页口径、总数或每页记录数发生变化');break
        ids=[r['service_id'] for r in p['orders']]
        if len(set(ids))!=len(ids) or seen.intersection(ids):issues.append('跨页服务单重复，停止拼接');break
        seen.update(ids);rows.extend(p['orders'])
    if error:issues.append(error)
    expected_pages=max(1,(total+size-1)//size) if total is not None else None
    complete=not issues and total is not None and len(pages)==expected_pages and len(seen)==total
    reasons=Counter();types=Counter();states=Counter();hotspots={};reason_known=0;amount_known=0;success_known=0;amount=Decimal(0);success_amount=Decimal(0)
    for row in rows:
        labels=row.get('reasons')
        if labels:reason_known+=1;reasons.update(set(labels))
        types[str(row.get('service_type_raw'))]+=1
        fields=row.get('status_fields',{});states[str(fields.get('afsServiceStatusName') or fields.get('afsServiceStatus') or '未知')]+=1
        refund=row.get('refund_fields',{});value=refund.get('refundAmount')
        try:
            if isinstance(value,bool) or value is None:raise InvalidOperation
            number=Decimal(str(value))
            if not number.is_finite() or number<0:raise InvalidOperation
            amount+=number;amount_known+=1
            if refund.get('refundStatusName')=='退款成功':success_amount+=number;success_known+=1
        except (InvalidOperation,ValueError):pass
        row_products=set()
        for item in row.get('items',[]):
            sku=str(item.get('wareId') or item.get('skuId') or '')
            if not sku or sku in row_products:continue
            row_products.add(sku);h=hotspots.setdefault(sku,{'official_ware_id':sku,'name':item.get('wareName') or item.get('skuName'),'service_count':0})
            h['service_count']+=1
    return {'status':'partial','platform':'jd','store_key':store,'date':day,'time_basis':'application_day',
        'whole_day_complete':complete,'official_total':total,'unique_service_count':len(seen),'missing_services':max(0,total-len(seen)) if total is not None else None,
        'pages_read':len(pages),'expected_pages':expected_pages,'page_size':size,'errors':issues,
        'unique_order_count':len({r['order_id'] for r in rows if r.get('order_id')}),'reason_known_services':reason_known,'reason_missing_services':len(rows)-reason_known,
        'reason_distribution':dict(reasons),'service_type_raw_distribution':dict(types),'service_state_distribution':dict(states),
        'refund_amount_known_services':amount_known,'refund_amount_missing_services':len(rows)-amount_known,'refund_amount_known_sum':float(amount),
        'refund_success_amount':float(success_amount),'refund_success_amount_known_services':success_known,
        'item_hotspots':sorted(hotspots.values(),key=lambda x:(-x['service_count'],x['official_ware_id'])),
        'orders':rows,'cohort_return_rate':None,'page_reports':[p['report_path'] for p in pages],
        'limitations':['按申请日的服务单集合；退款金额与状态是采集时快照，不与当日完结退款或销售额直接对账。',
          '只有whole_day_complete为true且missing_services=0才是整日服务单覆盖；退货归因模块仍partial。',
          '原因按完整官方标签计服务单数，不拆分标签；多原因可使类别计数合计高于服务单数。',
          '同订单可有多张服务单；商品热点按服务单关联计数，不把一张服务单金额复制分摊给多件商品。',
          '没有原付款队列及观察期分母，不计算真实退货率、净销售或利润。']}

def collect_all(day,store):
    from .api_client import APIClient
    pages=[];failure=None
    try:
        with APIClient({'platform':'jd','store_key':store},min_extension='0.9.13') as client:
            for index in range(1,2001):
                print(f'售后申请日{day}：读取第{index}页（100条/页）',flush=True)
                pages.append(collect(day,store,index,page_size=100,client=client))
                result=aggregate(pages,day,store)
                if result['errors'] or result['whole_day_complete']:break
            else:failure='达到登记分页上限，未完成全日覆盖'
    except Exception as exc:failure=str(exc)
    report=aggregate(pages,day,store,failure)
    folder=ROOT/'data/jd'/store.replace(':','_')/day/'after-sales-full'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');folder.mkdir(parents=True,exist_ok=False)
    report['report_path']=str(folder/'report.json');report['markdown_path']=str(folder/'report.md')
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    text=f"# 京东售后申请日复盘 {day}\n\n完整覆盖：{report['whole_day_complete']}；官方{report['official_total']}张，唯一服务单{report['unique_service_count']}张，缺失{report['missing_services']}张。\n\n"
    text+=f"原因已知{report['reason_known_services']}张，未知{report['reason_missing_services']}张。\n\n"
    text+='\n'.join(f'- {key}：{value}张' for key,value in report['reason_distribution'].items())+'\n\n'
    text+='\n'.join('- '+x for x in report['limitations']+report['errors'])+'\n'
    (folder/'report.md').write_text(text,encoding='utf-8')
    return {k:v for k,v in report.items() if k not in ('orders','item_hotspots','page_reports')}|{'item_hotspots_top10':report['item_hotspots'][:10]}
