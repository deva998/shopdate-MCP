"""Single created-day order pages, projected to business fields in the browser."""
from datetime import date,datetime,timedelta,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path
import hashlib,json,re,time,sys
from .api_client import ROOT

PAGE='https://shop.jd.com/jdm/trade/orders/order-list?tabType=allOrders'
URL='https://sff.jd.com/api?v=1.0&appId=COCX0HBWR4BA7RDVDBIQ&api=dsm.order.bff.orderListBffService.queryOrderPage'

def make_body(day,page=1):
    if date.fromisoformat(day).isoformat()!=day or type(page) is not int or not 1<=page<=1000:raise ValueError('订单日期或页码无效')
    body=json.loads((ROOT/'extension/unpacked/order-template.json').read_text(encoding='utf-8'))
    body['request']['data'].update(orderCreateTimeBegin=day+' 00:00:00',orderCreateTimeEnd=day+' 23:59:59',current=page)
    return body

def _keys(value,allowed):
    if not isinstance(value,dict) or set(value)-set(allowed):raise ValueError('订单字段未通过业务白名单，停止保存')

def _id(value):
    if isinstance(value,bool) or not re.fullmatch(r'[1-9]\d{0,19}',str(value)):raise ValueError('订单或商品编号无效')
    return str(value)

def _money(value):
    if value is None:return None
    if isinstance(value,bool):raise ValueError('订单金额无效')
    try:n=Decimal(str(value))
    except InvalidOperation:raise ValueError('订单金额无效') from None
    if not n.is_finite() or n<0:raise ValueError('订单金额无效')
    return format(n,'f')

def _time(value):
    if value is None or value=='':return None
    if isinstance(value,str):
        try:return datetime.fromisoformat(value.replace('Z','+00:00')).isoformat(sep=' ')
        except ValueError:raise ValueError('订单时间格式尚未核验') from None
    if type(value) is int and 946684800000<=value<4102444800000:
        return datetime.fromtimestamp(value/1000,timezone(timedelta(hours=8))).isoformat(sep=' ')
    raise ValueError('订单时间格式尚未核验')

def parse(payload,day,page,merchant_id,*,merchant_binding=None,page_size=10):
    make_body(day,page);_id(merchant_id)
    if page_size not in (10,50):raise ValueError('订单每页条数未登记')
    _keys(payload,('projection','code','data','schema'))
    if payload.get('projection')!='order-business-v1' or payload.get('code')!=200:raise ValueError('订单响应未通过浏览器业务投影')
    data=payload.get('data');_keys(data,('venderId','total','totalItem','totalReceivables','results'))
    response_merchant=data.get('venderId')
    if response_merchant is None:
        if merchant_binding!='same_origin_official_shop_information':raise ValueError('响应未提供商家编号，且缺少官方同源会话映射')
    elif _id(response_merchant)!=str(merchant_id):raise ValueError('订单商家与官方店铺映射不符')
    totals=[v for v in (data.get('total'),data.get('totalItem')) if v is not None]
    if any(type(v) is not int or v<0 for v in totals):raise ValueError('订单总数格式未核验')
    total=totals[0] if totals and len(set(totals))==1 else None
    rows=data.get('results')
    if not isinstance(rows,list) or len(rows)>page_size or (not rows and total not in (None,0) and (page-1)*page_size<total):raise ValueError('订单页为空、超出页大小或结构异常')
    orders=[];seen=set();counts={}
    for row in rows:
        _keys(row,('orderId','parentId','orderCreateTime','paymentConfirmTime','orderCompleteTime','skuTotalNum','orderStatusInfo','orderPaymentInfo','orderItems'))
        identifier=_id(row.get('orderId'))
        relationship={}
        if 'parentId' in row:
            parent=row['parentId']
            if type(parent) is int and abs(parent)>9007199254740991:raise ValueError('父订单编号超过浏览器安全整数范围')
            if parent is None or type(parent) in (str,int) and str(parent) in ('','0'):
                relationship={'parent_order_id':None,'parent_relation_status':'reported_empty_not_verified_root'}
            else:
                parent=_id(parent)
                if parent==identifier:raise ValueError('父订单编号自指')
                relationship={'parent_order_id':parent,'parent_relation_status':'reported_parent'}
        if identifier in seen:raise ValueError('订单页存在重复订单')
        seen.add(identifier);created=_time(row.get('orderCreateTime'))
        if not created or created[:10]!=day:raise ValueError('订单下单日期与任务不符')
        state=row.get('orderStatusInfo') or {};_keys(state,('orderStatus','orderStatusName'))
        payment=row.get('orderPaymentInfo') or {};_keys(payment,('receivables','shouldPay','orderSum','freight'))
        items=[]
        if not isinstance(row.get('orderItems'),list):raise ValueError('订单商品列表缺失')
        for item in row['orderItems']:
            _keys(item,('skuId','skuName','num','jdPrice','itemNum'))
            quantity=item.get('num')
            if quantity is not None and (type(quantity) is not int or quantity<0):raise ValueError('订单商品数量无效')
            items.append({'sku_id':_id(item.get('skuId')),'name':item.get('skuName'),'quantity':quantity,'listed_price':_money(item.get('jdPrice')),'item_num':item.get('itemNum')})
        label=state.get('orderStatusName');counts[label or '未知']=counts.get(label or '未知',0)+1
        orders.append({'order_id':identifier,'created_at':created,'payment_confirmed_at':_time(row.get('paymentConfirmTime')),'completed_at':_time(row.get('orderCompleteTime')),
            'status_code':state.get('orderStatus'),'status_name':label,'receivables':_money(payment.get('receivables')),
            'should_pay':_money(payment.get('shouldPay')),'order_sum':_money(payment.get('orderSum')),'freight':_money(payment.get('freight')),'items':items,**relationship})
    if total is not None and len(rows)>total:raise ValueError('订单记录数超过官方总数')
    known=[Decimal(row['receivables']) for row in orders if row['receivables'] is not None]
    complete=page==1 and total is not None and total==len(orders)
    return {'date':day,'page':page,'page_size':page_size,'orders':orders,'page_orders':len(orders),'total_orders':total,
        'merchant_id':str(merchant_id),'response_merchant_id':response_merchant,'merchant_binding':merchant_binding or 'response_vendor_and_official_information',
        'source_totals':{k:data.get(k) for k in ('total','totalItem')},'complete':complete,'status':'ok' if complete else 'partial',
        'page_receivables':format(sum(known,Decimal(0)),'f') if orders and len(known)==len(orders) else None,
        'source_reported_receivables':_money(data.get('totalReceivables')),'page_status_counts':counts,
        'time_basis':'order_created_day','status_as_of':'capture_time_not_historical_day_end',
        'next_page':page+1 if len(rows)==page_size and (total is None or page*page_size<total) else None,
        'definitions':['仅下单日筛选；状态为本次采集时状态，不是历史日末状态。','商家应收receivables，不当成买家实付；订单金额不重复分摊到每个SKU。','只读一页时不计算全日取消率、付款率；官方订单口径不强行等同商智成交口径。','未采集买家姓名、电话、地址、账号或留言；金额缺失不补0。']}

def aggregate_pages(pages):
    if not pages or pages[0]['page']!=1:raise ValueError('完整订单汇总必须从第1页开始')
    first=pages[0];orders=[];seen=set();counts={}
    for number,part in enumerate(pages,1):
        if part['page']!=number or any(part[k]!=first[k] for k in ('date','merchant_id','total_orders')):raise ValueError('订单分页不连续、店铺/日期/官方总数发生变化')
        if number<len(pages) and len(part['orders'])!=10:raise ValueError('订单非末页记录数不完整')
        for row in part['orders']:
            if row['order_id'] in seen:raise ValueError('订单跨页重复，不拼成完整数据')
            seen.add(row['order_id']);orders.append(row)
            label=row['status_name'] or '未知';counts[label]=counts.get(label,0)+1
    total=first['total_orders'];complete=total is not None and len(orders)==total
    if total is not None and len(orders)>total:raise ValueError('订单跨页记录超过官方总数')
    money=[Decimal(row['receivables']) for row in orders if row['receivables'] is not None]
    return {**first,'page':None,'scope':'created_day_all_pages','pages_read':len(pages),'orders':orders,'page_orders':len(orders),
        'fetched_orders':len(orders),'complete':complete,'status':'ok' if complete else 'partial',
        'page_receivables':format(sum(money,Decimal(0)),'f') if orders and len(money)==len(orders) else None,
        'source_reported_receivables':None,'page_status_counts':counts,
        'next_page':len(pages)+1 if not complete and len(pages[-1]['orders'])==10 else None,
        'definitions':first['definitions']+['订单编号去重后逐页核对官方总数；包含当前订单列表的父/拆单记录，不据此直接计算商智成交金额或有效成交率。','跨页状态是采集期间各页快照，不是数据库原子快照；按下单日筛选也不等于按支付日统计。']}

def aggregate_sweeps(sweeps):
    """Reconcile unstable offset pages against a stable official cohort count.

    Overlap alone is never evidence of completeness. At least one full sweep
    and exactly the official number of distinct IDs are required.
    """
    if not sweeps or not sweeps[0]:raise ValueError('订单核对必须从第1页开始')
    first=sweeps[0][0];total=first['total_orders'];size=first['page_size'];unique={};observations=0;completed=0
    for index,parts in enumerate(sweeps):
        if not parts or parts[0]['page']!=1:raise ValueError('订单补读必须从第1页开始')
        for page,part in enumerate(parts,1):
            if part['page']!=page or any(part[k]!=first[k] for k in ('date','merchant_id','total_orders','page_size')):raise ValueError('订单分页不连续、店铺/日期/官方总数或页大小发生变化')
            expected=min(size,max(0,total-(page-1)*size)) if total is not None else None
            if expected is not None and (len(part['orders'])!=expected or (total and page>(total+size-1)//size)):raise ValueError('订单页条数与官方总数不符')
            for row in part['orders']:
                previous=unique.get(row['order_id'])
                if previous and (previous['created_at']!=row['created_at'] or sorted((i['sku_id'],i['quantity']) for i in previous['items'])!=sorted((i['sku_id'],i['quantity']) for i in row['items'])):raise ValueError('同订单编号的下单时间或商品数量冲突')
                unique[row['order_id']]=row;observations+=1
        terminal=total is not None and parts[-1]['page']==max(1,(total+size-1)//size)
        if terminal:completed+=1
        elif index<len(sweeps)-1:raise ValueError('未读到末页，不开始下一轮')
    if total is not None and len(unique)>total:raise ValueError('唯一订单数超过官方总数，停止全量判定')
    rows=list(unique.values());complete=total is not None and len(rows)==total and completed>0
    counts={}
    for row in rows:
        label=row['status_name'] or '未知';counts[label]=counts.get(label,0)+1
    money=[Decimal(row['receivables']) for row in rows if row['receivables'] is not None]
    return {**first,'page':None,'scope':'created_day_all_pages','orders':rows,'page_orders':len(rows),'fetched_orders':len(rows),
        'pages_read':sum(map(len,sweeps)),'sweeps_started':len(sweeps),'completed_sweeps':completed,
        'duplicate_observations':observations-len(rows),'missing_orders':None if total is None else total-len(rows),
        'complete':complete,'status':'ok' if complete else 'partial','next_page':None,
        'page_receivables':format(sum(money,Decimal(0)),'f') if rows and len(money)==len(rows) else None,
        'source_reported_receivables':None,'page_status_counts':counts,
        'definitions':first['definitions']+['官方时间排序存在跨页重叠；完整遍历后按订单编号合并，缺单时从第1页补读；每页官方总数须一致，唯一编号数等于总数才判完整。',
          '同编号保留最近一次已核验业务快照；包含父/拆单记录，不据此直接计算商智成交金额或有效成交率。',
          '跨页状态是采集期间快照，不是历史日末或数据库原子快照；下单日不等于支付日。']}


def collect(day,store,page=1,*,all_pages=False):
    from .api_client import APIClient
    from .api_products import write_json
    if not re.fullmatch(r'jd:mall:\d+',store):raise ValueError('订单必须指定京东店铺')
    today=datetime.now(timezone(timedelta(hours=8))).date();selected=date.fromisoformat(day)
    if not today-timedelta(days=179)<=selected<today:raise ValueError('首期订单只支持近180日内的历史完整下单日')
    make_body(day,page)
    if all_pages and page!=1:raise ValueError('全量订单必须从第1页开始')
    folder=ROOT/'data/jd'/store.replace(':','_')/day/'order-list'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder.mkdir(parents=True,exist_ok=False)
    pages=[];sweeps=[[]];proofs=[];started=time.monotonic();stop_reason=None;failed_page=None
    with APIClient({'platform':'jd','store_key':store},min_extension='0.9.5') as client:
        current=page;last_request=None
        while True:
            try:
                if last_request is not None:time.sleep(max(0,2-(time.monotonic()-last_request)))
                last_request=time.monotonic()
                payload,proof=client.request('order-list',day,scope={'page':current})
                identity=proof['identity']
                if identity.get('merchant_identity_kind')!='official_shop_information':raise ValueError('订单缺少官方商家映射')
                part=parse(payload,day,current,identity.get('merchant_id'),merchant_binding=identity.get('merchant_binding'),page_size=make_body(day,current)['request']['data']['pageSize'])
                raw=client.last_response_text
                if not isinstance(raw,str) or hashlib.sha256(raw.encode()).hexdigest()!=proof['response_sha256']:raise ValueError('订单投影哈希不符')
                candidate=aggregate_sweeps(sweeps[:-1]+[sweeps[-1]+[part]]) if all_pages else part
                (folder/(f'sweep-{len(sweeps):02d}-page-{current:04d}-business.json' if all_pages else 'response-business.json')).write_text(raw,encoding='utf-8')
            except Exception as error:
                if not all_pages or not pages:raise
                # Keep the last verified prefix. Never include the rejected page
                # or suggest continuing past a failed request or identity check.
                failed_page=current;stop_reason='第'+str(current)+'页停止：'+str(error)
                report={**report,'complete':False,'status':'partial','next_page':None}
                break
            pages.append(part);sweeps[-1].append(part);proofs.append(proof);report=candidate
            if all_pages and (current==1 or current%25==0 or part['next_page'] is None):print(f"订单核对：第{len(sweeps)}轮第{current}页；唯一{len(report['orders'])}/{report['total_orders']}笔；重叠{report['duplicate_observations']}次",file=sys.stderr,flush=True)
            if not all_pages or report['complete']:break
            if part['total_orders'] is None:stop_reason='官方总数未明确，停止自动遍历';break
            if time.monotonic()-started>1800:stop_reason='达到30分钟后台读取上限，仍为部分覆盖';break
            if part['next_page'] is None:
                if len(sweeps)>=3:stop_reason='三轮核对后唯一订单仍少于官方总数，未完成全量';break
                sweeps.append([]);current=1;continue
            if current>=1000:stop_reason='达到单轮1000页读取上限，仍为部分覆盖';break
            current+=1
    report.update(platform='jd',store_key=store,captured_at=proofs[0]['request_started_at'],capture_finished_at=proofs[-1].get('received_at'),
        query_proof=proofs[0],report_path=str(folder/'report.json'),collection_seconds=round(time.monotonic()-started,3),collection_stop=stop_reason,failed_page=failed_page)
    if all_pages:report['query_proofs']=proofs
    if report['next_page']:report['next_call']={'platform':'jd','store':store,'command':'order-list','args':['--date',day,'--page',str(report['next_page'])]}
    write_json(folder/'report.json',report)
    if all_pages:return {k:v for k,v in report.items() if k not in ('orders','query_proofs')}|{'sample_orders':report['orders'][:3]}
    return report
