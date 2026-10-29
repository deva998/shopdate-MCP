"""Official tagged-new-product lists; never infer first listing date."""
from datetime import date,datetime,timezone
import copy,hashlib,json,re,uuid
from .api_client import ROOT,APIClient

ENDPOINT='https://szgateway.jd.com/szpaas/lowcode/szajax/query/markNewProduct.ajax'
PAGE='https://jdsz.jd.com/szweb/view/product/mark-new-product-temp.html'

def make_body(day,dimension,page):
    if date.fromisoformat(day).isoformat()!=day or dimension not in ('sku','spu') or type(page) is not int or not 1<=page<=1000:raise ValueError('新品日期、维度或页码无效')
    templates=json.loads((ROOT/'extension/unpacked/new-product-contracts.json').read_text(encoding='utf-8'))
    body=copy.deepcopy(templates[dimension])
    for item in body['filterList']:
        if item['propertyName']=='dt':item['values']=[day]
    body['commonParam'].update(date=day,startDate=day,endDate=day,page=page,traceId=str(uuid.uuid4()),batchId=str(uuid.uuid4()))
    return body

def parse_page(payload,dimension):
    if payload.get('header',{}).get('code')!='200' or payload.get('errors'):raise ValueError('新品业务状态失败')
    body=payload.get('body') or {};meta=(body.get('metaData') or {}).get('meta')
    data=body.get('data');size=body.get('size')
    if dimension not in ('sku','spu') or not isinstance(meta,list) or not isinstance(data,list) or type(size) is not int or not 0<=size<=100000:raise ValueError('新品结构或总数无效')
    fields=[item.get('di') for item in meta]
    flags=['jdr_sch_sku_'+x+'_newproduct_flag' for x in 'abc']
    if not all(isinstance(x,str) for x in fields) or len(set(fields))!=len(fields) or any(x not in fields for x in [dimension+'_id',*flags]):raise ValueError('缺少新品维度或标签')
    output=[];seen=set()
    for row in data:
        if not isinstance(row,list) or len(row)!=len(fields):raise ValueError('新品列宽不符')
        values=dict(zip(fields,row));identifier=values[dimension+'_id']
        if not isinstance(identifier,str) or not re.fullmatch(r'\d{1,32}',identifier)  :raise ValueError('新品编号缺失或重复')
        if any(values[f] not in ('0','1') for f in flags):raise ValueError('未知新品标签值')
        key=(identifier,*(values[f] for f in flags))
        if key in seen:raise ValueError('新品分组重复')
        seen.add(key)
        output.append({'id':identifier,'flags':{x:values[f] for x,f in zip('abc',flags)},'metrics':{f:v for f,v in values.items() if f not in [dimension+'_id',*flags]}})
    return output,size

def collect(day,store,dimension='sku',*,client=None):
    make_body(day,dimension,1)
    if client is None:
        with APIClient({'platform':'jd','store_key':store},min_extension='0.8.3') as active:return collect(day,store,dimension,client=active)
    folder=ROOT/'data/jd'/store.replace(':','_')/day/('new-products-'+dimension)/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder.mkdir(parents=True,exist_ok=False)
    rows=[];seen=set();proofs=[];expected=None;errors=[]
    try:
        for page in range(1,1001):
            payload,proof=client.request('new-products',day,dimension=dimension,scope={'page':page})
            raw=client.last_response_text
            if proof['identity'].get('store_key')!=store or proof['identity'].get('platform')!='jd' or hashlib.sha256(raw.encode()).hexdigest()!=proof['response_sha256']:raise ValueError('新品店铺或正文证据不符')
            target=folder/f'page-{page:04}.json';target.write_text(raw,encoding='utf-8')
            proofs.append({**proof,'response_path':str(target)})
            batch,total=parse_page(payload,dimension)
            if expected is None:expected=total
            if total!=expected or len(batch)>100 or (not batch and len(rows)<expected):raise ValueError('新品分页总数变化或页面缺失')
            if any((item['id'],*item['flags'].values()) in seen for item in batch):raise ValueError('新品跨页重复，不能认定完整')
            rows.extend(batch);seen.update((item['id'],*item['flags'].values()) for item in batch)
            if len(rows)>expected:raise ValueError('新品行数超过官方总数')
            if len(rows)==expected:break
        else:raise ValueError('达到1000页上限，未取全')
    except (ValueError,RuntimeError,OSError,TimeoutError) as error:errors.append(str(error))
    report={'platform':'jd','store_key':store,'date':day,'dimension':dimension,'status':'partial' if errors else 'ok','complete':not errors,'official_total':expected,'captured_rows':len(rows),'unique_products':len({item['id'] for item in rows}),'errors':errors,'cohort_definition':'official_ABC_tagged_new_products','notes':['非首次上架日期队列；不推定上架30天内','主列表与推荐补充指标分开；不混用搜索与推荐曝光','总数是商品与ABC标签组合分组行数，非唯一商品数；不擅自合并不同标签组','空值保留；按商品汇总访客不等于全店去重访客'],'rows':rows,'requests':proofs}
    target=folder/'report.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    return {k:v for k,v in report.items() if k not in ('rows','requests')}|{'report_path':str(target),'preview':rows[:3]}
