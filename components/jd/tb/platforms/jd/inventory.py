"""Current SKU total-stock snapshots, scoped to products in verified JD exports."""
from datetime import datetime,timezone,timedelta,date
from pathlib import Path
import hashlib,json,re
from .api_client import ROOT

PAGE='https://wares-jdm.jd.com/ware/wareList?activeTab=OnsaleWare&businessModel=0'
URL='https://sff.jd.com/api?v=1.0&appId=3MC69M4R3HFKCQ4S01DN&api=dsm.product.manage.SkuInfoReadViewService.querySkuList'

def make_body(product):
    if not isinstance(product,str) or not re.fullmatch(r'[1-9]\d{0,19}',product) or int(product)>9007199254740991:raise ValueError('无效的商品编码')
    return {'skuListQueryReq':{'productId':int(product),'skuName':None,'skuStatusList':[4],'categoryIds':[],
        'brandIdList':[],'itemNum':None,'skuType':None,'startCreated':None,'endCreated':None,
        'startModified':None,'endModified':None,'sortMap':{'created':'asc'},'supplyVenderId':None},
        'accessContext':{'source':'web','businessModel':'0','proxyBelongBizId':'','originType':None}}

def parse(payload,product):
    make_body(product)
    if type(payload.get('code')) is not int or payload['code']!=200:raise ValueError('库存业务状态失败')
    data=payload.get('data')
    if not isinstance(data,dict) or data.get('status')=='session_close' or data.get('api')=='openUrl':raise ValueError('收到会话控制响应，未取得库存；请在官方页面检查登录/验证状态')
    rows=data.get('data');total=data.get('totalCount')
    if not isinstance(rows,list) or type(total) is not int or not 0<=total<=2000 or len(rows)!=total or data.get('pages') not in (None,1) or data.get('pageNo') not in (None,1):raise ValueError('SKU列表缺失、分页未核验或记录不完整')
    items=[];seen=set()
    for row in rows:
        identifier=str(row.get('skuId',''))
        if str(row.get('productId'))!=product or not re.fullmatch(r'[1-9]\d{0,19}',identifier) or identifier in seen or row.get('skuStatus')!=4:raise ValueError('SKU商品归属、编号或状态不符')
        seen.add(identifier);stock=row.get('stockNum')
        if stock is not None and (type(stock) is not int or stock<0):raise ValueError('库存数量不是已核验的非负整数')
        aliases=row.get('saleAttrAlias')
        if not isinstance(aliases,list) or any(not isinstance(x,str) for x in aliases):raise ValueError('SKU规格结构不符')
        attributes={}
        for attribute in row.get('saleAttrs') or []:
            if not isinstance(attribute,dict):continue
            for encoded in attribute.get('attrValueAlias') or []:
                try:values=json.loads(encoded)
                except (ValueError,TypeError):continue
                if not isinstance(values,list):continue
                for value in values:
                    if not isinstance(value,dict) or not isinstance(value.get('modelName'),str) or not isinstance(value.get('value'),str):continue
                    attributes.setdefault(value['modelName'],[])
                    if value['value'] not in attributes[value['modelName']]:attributes[value['modelName']].append(value['value'])
        def single(key):return attributes[key][0] if len(attributes.get(key,[]))==1 else None
        items.append({'product_id':product,'sku_id':identifier,'name':row.get('skuName'),
            'merchant_sku_code':row.get('outerId'),'sale_attributes':aliases,'total_stock':stock,
            'attributes':attributes,'color':single('颜色'),'size':single('通用尺码') or single('尺码'),'sku_status':4})
    known=[r['total_stock'] for r in items if r['total_stock'] is not None]
    return {'status':'empty' if not items else 'partial' if len(known)!=len(items) else 'ok',
        'product_id':product,'scope':'sku_status_4_only','sku_count':len(items),'complete_for_query':True,
        'known_total_stock':sum(known),'total_stock':sum(known) if items and len(known)==len(items) else None,
        'zero_stock_skus':sum(v==0 for v in known),'unknown_stock_skus':len(items)-len(known),
        'stock_updated_at':None,'available_stock':None,'items':items,
        'definition':'官方商品列表总库存stockNum；筛选skuStatusList=[4]，不代表所有状态SKU。不是可售/锁定/预占库存。modified和onlineTime不是库存专用更新时间。空值不补零，空列表不等于零库存。'}

def collect(product,store,evidence_day,*,client=None,batch=None,last=False):
    from .product_test import load_day
    from .api_client import APIClient
    from .api_products import write_json
    make_body(product);date.fromisoformat(evidence_day)
    if not re.fullmatch(r'jd:mall:\d+',store):raise ValueError('库存必须绑定京东店铺')
    records,ownership=load_day(evidence_day,store)
    if product not in records:raise ValueError('商品不在指定店铺已核验的官方导出中，停止库存查询')
    ownership.pop('derived_zero_evidence',None)
    now=datetime.now(timezone(timedelta(hours=8)));today=now.date().isoformat()
    from contextlib import nullcontext
    with (APIClient({'platform':'jd','store_key':store},min_extension='0.9.6') if client is None else nullcontext(client)) as active:
        scope={'product_id':product}
        if batch is not None:scope.update(batch=batch,last=last)
        payload,proof=active.request('inventory-sku',today,scope=scope)
        raw=active.last_response_text
        if not isinstance(raw,str) or hashlib.sha256(raw.encode()).hexdigest()!=proof['response_sha256']:raise ValueError('库存原文哈希不符')
        report=parse(payload,product)
    folder=ROOT/'data/jd'/store.replace(':','_')/today/'inventory'/product/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder.mkdir(parents=True,exist_ok=False);(folder/'response.json').write_text(raw,encoding='utf-8')
    report.update(platform='jd',store_key=store,date=today,acquisition='registered-api',
        captured_at=proof['request_started_at'],ownership_date=evidence_day,ownership=ownership,
        query_proof=proof,report_path=str(folder/'report.json'))
    write_json(folder/'report.json',report)
    return report

def verified_snapshot(path,store,*,root=None,now=None,ownership_cache=None):
    from .product_test import load_day
    root=Path(root) if root is not None else ROOT
    ownership_cache={} if ownership_cache is None else ownership_cache
    path=Path(path);r=json.loads(path.read_text(encoding='utf-8'));proof=r['query_proof'];product=r['product_id']
    if r.get('platform')!='jd' or r.get('store_key')!=store or proof.get('source')!='registered-api' or proof.get('case')!='inventory-sku' or proof.get('identity',{}).get('platform')!='jd' or proof.get('identity',{}).get('store_key')!=store or proof.get('request_body')!=make_body(product) or r.get('captured_at')!=proof.get('request_started_at'):raise ValueError('库存身份、时间或请求不符')
    raw=(path.parent/'response.json').read_text(encoding='utf-8')
    if hashlib.sha256(raw.encode()).hexdigest()!=proof.get('response_sha256'):raise ValueError('库存原文哈希不符')
    expected=parse(json.loads(raw),product)
    # Rebuild optional display attributes for snapshots captured before this parser update.
    comparison={k:v for k,v in expected.items() if k!='items'}
    if any(r.get(k)!=v for k,v in comparison.items()):raise ValueError('库存报告与原文不符')
    original=[{k:v for k,v in item.items() if k not in ('attributes','color','size')} for item in expected['items']]
    saved=[{k:v for k,v in item.items() if k not in ('attributes','color','size')} for item in r['items']]
    if saved!=original:raise ValueError('库存SKU报告与原文不符')
    if r['ownership_date'] not in ownership_cache:ownership_cache[r['ownership_date']]=load_day(r['ownership_date'],store,root=root)[0]
    if product not in ownership_cache[r['ownership_date']]:raise ValueError('库存商品未通过店铺导出归属核验')
    captured=datetime.fromisoformat(r['captured_at'].replace('Z','+00:00'))
    if not 0<=((now or datetime.now(timezone.utc))-captured).total_seconds()<=900:raise ValueError('库存快照超过15分钟或时间无效，请重新读取')
    return {**r,**expected,'report_path':str(path)}


def context(day,store,products,*,root=None,now=None,limit=10):
    """Attach only fresh, replayed snapshots; never implicitly query a new platform."""
    root=Path(root) if root is not None else ROOT
    if not re.fullmatch(r'jd:mall:\d+',store):raise ValueError('库存必须绑定京东店铺')
    if type(limit) is not int or not 1<=limit<=60:raise ValueError('库存选择上限应为1至60的整数')
    eligible=list(dict.fromkeys(str(i) for i in products));wanted=eligible[:limit]
    snapshots=[];missing=[];invalid=[];ownership_cache={}
    from .product_test import load_day
    for product in wanted:
        make_body(product)
        paths=sorted((root/'data/jd'/store.replace(':','_')).glob('*/inventory/'+product+'/*/report.json'),reverse=True)
        if not paths:missing.append(product);continue
        try:
            r=verified_snapshot(paths[0],store,root=root,now=now,ownership_cache=ownership_cache)
            if r['product_id']!=product:raise ValueError('库存商品与选择商品不符')
            snapshots.append({k:r[k] for k in ('product_id','status','sku_count','total_stock','zero_stock_skus','unknown_stock_skus','scope','captured_at','report_path')})
        except (ValueError,KeyError,TypeError,OSError) as error:invalid.append({'product_id':product,'reason':str(error)})
    unavailable=missing+[r['product_id'] for r in invalid]
    incomplete=[r['product_id'] for r in snapshots if r['status']!='ok' or r['total_stock'] is None]
    return {'status':'partial' if unavailable or incomplete else 'ok' if snapshots else 'not_requested',
        'scope':'selected_products_current_snapshot','analysis_date':day,'selected_products':len(wanted),
        'eligible_products':len(eligible),'unselected_products':len(eligible)-len(wanted),
        'all_candidates_covered':bool(eligible) and len(eligible)==len(wanted) and not unavailable and not incomplete,
        'snapshots':snapshots,'missing_products':missing,'invalid_products':invalid,
        'incomplete_products':incomplete,'complete_quantity_products':len(snapshots)-len(incomplete),
        'next_calls':[{'platform':'jd','store':store,'command':'inventory-sku','args':['--product-id',p,'--date',day]} for p in (unavailable+incomplete)[:3]],
        'limitation':f'仅所选商品当前库存快照，本次选择上限{limit}件、有效期15分钟；不是统计日历史库存，不用于证明历史下滑原因。总库存不等于可售库存，零库存SKU只能作为当前断码核查线索。'}

def ensure_context(day,store,products,*,limit=10):
    """Fill only this report's bounded selection; context() stays read-only."""
    import sys,time
    products=list(products);before=context(day,store,products,limit=limit)
    pending=list(dict.fromkeys(before['missing_products']+
        [r['product_id'] for r in before['invalid_products']]+before['incomplete_products']))
    receipts=[];error=None;started=time.monotonic()
    from contextlib import ExitStack
    import uuid
    attempted=[]
    def fill(selection):
        nonlocal error
        batch=uuid.uuid4().hex if limit>10 else None;client=None
        with ExitStack() as stack:
            for index,product in enumerate(selection):
                attempted.append(product)
                print('自动补齐当前库存：'+product,file=sys.stderr,flush=True)
                try:
                    if batch and client is None:
                        from .api_client import APIClient
                        client=stack.enter_context(APIClient({'platform':'jd','store_key':store},min_extension='0.9.10'))
                    result=collect(product,store,day,client=client,batch=batch,last=index==len(selection)-1) if batch else collect(product,store,day)
                    receipts.append({'product_id':product,'status':result['status'],'report_path':result['report_path']})
                except (ValueError,RuntimeError,TimeoutError,OSError) as exc:
                    error={'product_id':product,'reason':str(exc)}
                    break
    fill(pending)
    # Recheck against the completion clock, never a frozen task-start time.
    after=context(day,store,products,limit=limit)
    # A reused snapshot can expire while other products are being fetched.
    # Fill that newly stale subset once, never loop over earlier fresh reads.
    late=[] if error else [p for p in dict.fromkeys(after['missing_products']+[r['product_id'] for r in after['invalid_products']]+after['incomplete_products']) if p not in attempted]
    if late:
        pending+=late;fill(late)
        after=context(day,store,products,limit=limit)
    after['auto_refresh']={'status':'stopped' if error else 'complete' if after['status'] in ('ok','not_requested') else 'partial',
        'requested_products':len(pending),'receipts':receipts,'error':error,
        'unattempted_products':[p for p in pending if p not in attempted],
        'completion_refresh_products':len(late),
        'elapsed_ms':round((time.monotonic()-started)*1000)}
    return after


def markdown(result):
    if not result:return ''
    lines=['','## 当前库存核验',result['limitation'],
        f"候选商品{result.get('eligible_products',result['selected_products'])}件；本次选择{result['selected_products']}件；未选择{result.get('unselected_products',0)}件。",
        f"所选商品{result['selected_products']}件；原文已核验快照{len(result['snapshots'])}件；空集合或数量缺失{len(result.get('incomplete_products',[]))}件；缺失{len(result['missing_products'])}件；无效或过期{len(result['invalid_products'])}件。",
        '| 商品编码 | 总库存 | 库存为0的SKU数 | 采集时间 |','|---|---:|---:|---|']
    for row in result['snapshots']:
        quantity='缺失' if row['total_stock'] is None else str(row['total_stock'])
        lines.append(f"| {row['product_id']} | {quantity} | {row['zero_stock_skus']} | {row['captured_at']} |")
        lines.append('证据：'+row['report_path'])
    refresh=result.get('auto_refresh')
    if refresh:
        lines.append(f"自动补取计划{refresh['requested_products']}件，已保存{len(refresh['receipts'])}件；状态：{refresh['status']}。")
        if refresh.get('error'):lines.append('本轮补取已停止：'+refresh['error']['reason']+'；未完成商品不作为已知库存。')
    lines.append('本范围仅需当前SKU库存，不要求历史库存；标明快照时间，未取得数量不补零，当前总库存不改称可售库存。')
    return '\n'.join(lines)+'\n'
