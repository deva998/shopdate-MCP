"""Registered browser-session API requests. No credentials leave the browser."""
from dataclasses import replace
from datetime import date,datetime,timedelta,timezone
import hashlib,json,re,time,uuid
from pathlib import Path
from urllib.parse import urlsplit
from ...core.bridge import BridgeServer
from ...core.stores import verify_identity
from .platform import JD
from .product_downloads import export_prefix

ROOT=Path(__file__).resolve().parents[3]


def request_headers(path,*,timestamp=None,request_id=None):
    timestamp=int(time.time()*1000) if timestamp is None else timestamp
    request_id=str(uuid.uuid4()) if request_id is None else request_id
    value=f'{path}{request_id}{timestamp}372ad2c2b6'
    return {'uuid':request_id,'User-mup':str(timestamp),'User-mnp':hashlib.md5(value.encode()).hexdigest(),'X-Requested-With':'XMLHttpRequest'}


def make_job(key,day,identity,*,task=None,dimension=None,scope=None):
    contracts=json.loads((ROOT/'extension/unpacked/report-contracts.json').read_text(encoding='utf-8'))
    parsed=date.fromisoformat(day)
    if parsed.isoformat()!=day:raise ValueError('日期格式应为YYYY-MM-DD')
    if identity.get('platform')!='jd' or not re.fullmatch(r'jd:mall:\d+',identity.get('store_key','')):raise ValueError('必须指定京东店铺')
    routes={
      'overview':('POST',contracts['overview']['endpoint']),
      'overview-realtime':('POST',contracts['overview']['endpoint']),
      'task-list':('GET','https://szgateway.jd.com/api/common/downloadCenter/getTaskList.ajax'),
      'source-dictionary':('GET','https://szgateway.jd.com/api/lowcode/common/getDimensionTree.ajax?startDimName=jdr_sch_traffic_cha_last_field_src_rmad_sz_1&endDimName=jdr_sch_traffic_cha_last_field_src_rmad_sz_4')}
    if key in ('traffic-level1','traffic-level2'):routes[key]=('POST',contracts[key]['endpoint'])
    if key=='traffic-tree':routes[key]=('POST',contracts['traffic-level1']['endpoint'])
    if key=='traffic-channel':
        from .traffic_channels import contract
        routes[key]=('POST',contract()['endpoint'])
    if key=='inventory-sku':
        from .inventory import URL
        routes[key]=('POST',URL)
    if key in ('order-list','order-lookup'):
        from .orders import URL
        routes[key]=('POST',URL)
    if key=='after-sales-list':
        from .after_sales import URL
        routes[key]=('POST',URL)
    if key=='export-submit':
        if dimension not in ('spu','sku'):raise ValueError('导出必须指定SPU或SKU')
        routes[key]=('POST','https://szgateway.jd.com/api/lowcode/download/productDetail/table/offlineProductTable.ajax')
    if key=='task-file':
        if not isinstance(task,dict) or task.get('taskName')!=export_prefix(identity['store_key'],day) or type(task.get('taskStatues')) is not int or task.get('taskStatues')!=2 or not re.fullmatch(r'\d{16,24}',str(task.get('taskId',''))):raise ValueError('导出任务店铺、日期或状态不符')
        routes[key]=('GET','https://szgateway.jd.com/api/common/downloadCenter/getFileLink.ajax?taskId='+str(task['taskId']))
    if key=='new-products':
        from .new_products import ENDPOINT
        routes[key]=('POST',ENDPOINT)
    if key.startswith('industry-'):
        from .industry import ROUTES
        if key in ROUTES:routes[key]=ROUTES[key][:2]
    if key=='business-stats':
        from .business_stats import CONTRACTS as BUSINESS, validate, url
        if not isinstance(scope,dict) or set(scope)!={'report','params'}:raise ValueError('专题统计范围无效。')
        values=validate(scope['report'],scope['params'],day)
        if scope['report'].startswith('compete-compare-') and values['selfShopId']!=[identity['store_key'].removeprefix('jd:mall:')]:raise ValueError('竞店对比本店参数不符。')
        routes[key]=(BUSINESS[scope['report']]['method'],url(scope['report'],values))
    if key=='shop-insights':
        from .shop_insights import make_url,validate_params,historical_day
        historical_day(day)
        if not isinstance(scope,dict) or set(scope)!={'report','params'}:raise ValueError('类目/用户范围无效。')
        params=validate_params(scope['report'],scope['params'])
        from .user_analysis import CONTRACTS as USER_CONTRACTS
        if scope['report']!='user-dates' and USER_CONTRACTS.get(scope['report'],{}).get('schema') not in ('snapshot','fixed-meta','audience-system','member-industry-categories') and params['endDate']!=day:raise ValueError('类目/用户查询日期不符。')
        routes[key]=(USER_CONTRACTS.get(scope['report'],{}).get('method','GET'),make_url(scope['report'],params))
    if key not in routes:raise ValueError('未登记的接口验证')
    method,url=routes[key]
    page=contracts['traffic-level1' if key=='source-dictionary' or key.startswith('traffic-') else 'products-spu']['page']
    job={'operation':'api-probe','transport':'background-native','report_key':'overview','probe_key':key,'url':url,'method':method,
      'launch':page,'expected_store':identity,'requested_after':datetime.now(timezone.utc).isoformat(timespec='milliseconds'),'probe_headers':request_headers(urlsplit(url).path)}
    if key=='business-stats':
        job.update(launch=BUSINESS[scope['report']]['page'],business_report=scope['report'],business_params=values,business_date=day)
        if method=='POST':job['body']=json.dumps(values,ensure_ascii=False)
        if BUSINESS[scope['report']].get('schema')=='oneservice':job['probe_headers']['resappkey']=values['commonParam']['resAppKey']
    if key=='shop-insights':
        from .shop_insights import ROUTES
        job.update(launch=ROUTES[scope['report']][1],insights_report=scope['report'],insights_params=scope['params'])
        if method=='POST':
            from .user_metrics import make_body,CONTRACTS as METRIC_CONTRACTS
            job['body']=json.dumps(make_body(scope['report'],params),ensure_ascii=False)
            job['probe_headers']['resappkey']=METRIC_CONTRACTS[scope['report']]['template']['commonParam']['resAppKey']
    if key.startswith('industry-'):
        from .industry import ROUTES,validate_request
        job['launch']=ROUTES[key][2]
        if key!='industry-options':
            if not isinstance(scope,dict) or set(scope)!={'request'}:raise ValueError('行业查询必须指定已核验请求体。')
            body=validate_request(scope['request'])
            if body['startDate']!=day:raise ValueError('行业查询日期不符。')
            job['body']=json.dumps(body,ensure_ascii=False)
    if key in ('overview','export-submit','traffic-level1','traffic-level2','traffic-tree'):
        template=contracts['traffic-level1' if key=='traffic-tree' else key if key!='export-submit' else 'products-'+dimension]['template']
        body={**template,'startDate':day,'endDate':day,'compareStartDate':(parsed-timedelta(days=1)).isoformat(),'compareEndDate':(parsed-timedelta(days=1)).isoformat()}
        if key=='export-submit':body.update(trendType=None,cmpFlag=0);job['export_dimension']=dimension
        if key=='traffic-tree':
            if not isinstance(scope,dict) or set(scope)!={'level','parents','page'} or type(scope['level']) is not int or not 1<=scope['level']<=4 or type(scope['page']) is not int or not 1<=scope['page']<=1000 or not isinstance(scope['parents'],list) or len(scope['parents'])!=scope['level']-1 or any(not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_]{1,32}',value) for value in scope['parents']):raise ValueError('来源树范围无效')
            field='jdr_sch_traffic_cha_last_field_src_rmad_sz_'+str(scope['level'])
            body.update(groups=[field],attributes=[field],pageIndex=scope['page'])
            for index,value in enumerate(scope['parents'],1):body['flowSrcId'+str(index)]=[value]
            job['traffic_scope']=scope
        job['body']=json.dumps(body,ensure_ascii=False)
    if key=='new-products':
        from .new_products import PAGE,make_body
        if not isinstance(scope,dict) or set(scope)!={'page'}:raise ValueError('新品分页范围无效')
        job.update(launch=PAGE,new_dimension=dimension,body=json.dumps(make_body(day,dimension,scope['page']),ensure_ascii=False))
    if key=='traffic-channel':
        from .traffic_channels import PAGE,make_body
        if not isinstance(scope,dict) or set(scope)!={'channel'}:raise ValueError('终端范围无效')
        job.update(launch=PAGE,channel_scope=scope,body=json.dumps(make_body(day,scope['channel']),ensure_ascii=False))
    if key=='task-file':job.update(export_task={**task,'taskId':str(task['taskId'])},export_day=day)
    if key=='overview-realtime':
        from .realtime import make_body,contract
        body=make_body()
        if body['startDate'][:10]!=day:raise ValueError('实时概况只支持北京时间今天')
        job.update(launch=contract()['page'],body=json.dumps(body,ensure_ascii=False))
    if key=='inventory-sku':
        from .inventory import PAGE,make_body
        if not isinstance(scope,dict) or set(scope) not in ({'product_id'},{'product_id','batch','last'}):raise ValueError('库存查询范围无效')
        if 'batch' in scope:
            if not re.fullmatch(r'[0-9a-f]{32}',str(scope['batch'])) or type(scope['last']) is not bool:raise ValueError('库存批次无效')
            job.update(inventory_batch=scope['batch'],inventory_batch_last=scope['last'])
        job.update(launch=PAGE,inventory_product_id=scope['product_id'],body=json.dumps(make_body(scope['product_id']),ensure_ascii=False))
        job.pop('probe_headers',None)
    if key=='after-sales-list':
        from .after_sales import PAGE
        if not isinstance(scope,dict) or set(scope) not in ({'page'},{'page','page_size'}) or type(scope['page']) is not int or not 1<=scope['page']<=2000 or type(scope.get('page_size',10)) is not int or scope.get('page_size',10) not in (10,100):raise ValueError('售后分页范围无效')
        job.update(launch=PAGE,afs_date=day,afs_page=scope['page'],afs_page_size=scope.get('page_size',10))
        job.pop('probe_headers',None)
    if key=='order-list':
        from .orders import PAGE,make_body
        if not isinstance(scope,dict) or set(scope)!={'page'}:raise ValueError('订单分页范围无效')
        job.update(launch=PAGE,order_scope={'date':day,'page':scope['page']},body=json.dumps(make_body(day,scope['page']),ensure_ascii=False))
        job.pop('probe_headers',None)
    if key=='order-lookup':
        from .orders import PAGE
        from .refund_enrichment import make_lookup_body
        if not isinstance(scope,dict) or set(scope)!={'order_ids'}:raise ValueError('原订单查询范围无效')
        job.update(launch=PAGE,lookup_scope={'end_day':day,'order_ids':scope['order_ids']},body=json.dumps(make_lookup_body(day,scope['order_ids']),ensure_ascii=False))
        job.pop('probe_headers',None)
    return job


class APIClient:
    def __init__(self,identity,bridge=None,*,min_extension='0.8.2'):
        self.identity=identity;self.audit=[];self.owns_bridge=bridge is None;self.started=False
        if bridge is None:
            from ...runtime import configure
            configure()
        self.bridge=bridge if bridge is not None else BridgeServer(replace(JD,min_extension=min_extension))
        self.last_response_text=None;self.awake=None;self.power_state={}

    def __enter__(self):
        if self.owns_bridge:
            from .power import SystemAwake
            self.awake=SystemAwake();self.power_state=self.awake.__enter__()
            try:self.bridge.start();self.started=True
            except Exception:
                try:self.bridge.server_close()
                finally:self.awake.__exit__(None,None,None)
                raise
        return self

    def __exit__(self,*_):
        try:
            if self.started:self.bridge.stop()
        finally:
            if self.awake:self.awake.__exit__(None,None,None)

    def request(self,key,day,*,task=None,dimension=None,scope=None):
        started=time.monotonic()
        recoverable_reads={'overview','overview-realtime','traffic-level1','traffic-level2','traffic-tree','traffic-channel','source-dictionary','new-products','task-list','task-file'}
        attempt_errors=[]
        for attempt in range(2 if key in recoverable_reads or key=='inventory-sku' else 1):
            job=make_job(key,day,self.identity,task=task,dimension=dimension,scope=scope);job['operation']='registered-api'
            result=self.bridge.submit(job,60)
            error=result.get('error')
            if not error:break
            attempt_errors.append({'error':str(error),'dispatched_at':job['requested_after']})
            # The worker has returned this observed page timeout and evicted
            # its page cache. One pure-read retry may recover on a responsive
            # page. Export submission, identity/business errors and bridge
            # timeouts are never replayed here.
            if attempt==0 and key in recoverable_reads and str(error).startswith('页面执行超时：request:'+key+'；'):continue
            # DSM documents 601 as a backend business timeout. Inventory is a
            # fixed pure read; retry exactly once, never auth/control errors.
            if attempt==0 and key=='inventory-sku' and str(error).startswith('库存请求失败：未取得库存列表：code=601；'):continue
            raise ValueError(str(error))
        verify_identity(self.identity,result.get('identity'))
        if result.get('source')!='registered-api' or result.get('transport')!='registered-api' or result.get('status')!=200:
            raise ValueError(f"接口响应来源或状态不符：source={result.get('source')!r}, transport={result.get('transport')!r}, status={result.get('status')!r}, fields={sorted(result)}")
        try:request_time=datetime.fromisoformat(result['request_started_at'].replace('Z','+00:00'));issued=datetime.fromisoformat(job['requested_after'])
        except (KeyError,ValueError,TypeError):raise ValueError('缺少真实请求开始时间') from None
        if not 0<=(request_time-issued).total_seconds()<=60:raise ValueError('接口请求时间过期或早于任务')
        payload=json.loads(result['text'])
        if key=='business-stats':
            self.last_response_text=result['text']
            self.last_response_context={'case':key,'date':day,'business_report':scope['report'],'request_params':scope['params'],
                'identity':result['identity'],'source':'registered-api','dispatched_at':job['requested_after'],
                'request_started_at':result['request_started_at'],'response_sha256':hashlib.sha256(result['text'].encode()).hexdigest()}
        if key=='inventory-sku':
            from .inventory import parse
            parse(payload,scope['product_id'])
        elif key=='order-list':
            from .orders import parse
            if result['identity'].get('merchant_identity_kind')!='official_shop_information':raise ValueError('缺少订单官方商家映射')
            parse(payload,day,scope['page'],result['identity'].get('merchant_id'),merchant_binding=result['identity'].get('merchant_binding'),page_size=json.loads(job['body'])['request']['data']['pageSize'])
        elif key=='order-lookup':
            from .refund_enrichment import parse_lookup
            if result['identity'].get('merchant_identity_kind')!='official_shop_information':raise ValueError('缺少原订单官方商家映射')
            parse_lookup(payload,day,scope['order_ids'],result['identity'].get('merchant_id'),merchant_binding=result['identity'].get('merchant_binding'))
        elif key=='after-sales-list':
            from .after_sales import parse
            if result['identity'].get('merchant_identity_kind')!='official_shop_information':raise ValueError('缺少售后官方商家映射')
            parse(payload,day,scope['page'],page_size=scope.get('page_size',10))
        elif key=='business-stats':
            from .business_stats import business_body
            business_body(payload,scope['report'])
        elif key=='shop-insights':
            from .user_metrics import CONTRACTS as METRIC_CONTRACTS
            if scope['report'] in METRIC_CONTRACTS:
                from .user_metrics import business_body
            else:
                from .shop_insights import business_body
            business_body(payload)
        elif payload.get('header',{}).get('code')!=('200' if key=='new-products' else 0) or payload.get('errors'):raise ValueError('接口业务状态不成功')
        proof={'case':key,'date':day,'source':'registered-api','identity':result['identity'],'dispatched_at':job['requested_after'],
          'request_started_at':result['request_started_at'],'received_at':result.get('received_at'),'elapsed_ms':round((time.monotonic()-started)*1000),
          'response_sha256':hashlib.sha256(result['text'].encode()).hexdigest(),'request_body':json.loads(job['body']) if job.get('body') else None,
          'task_id':str(task['taskId']) if task else None,'bridge_timings':result.get('bridge_timings'),'execution_page':result.get('execution_page'),
          'request_mode':result.get('request_mode','registered-fetch'),
          'raw_response_sha256':result.get('raw_response_sha256'),
          'attempts':len(attempt_errors)+1,'attempt_errors':attempt_errors,
          'system_awake_during_request':{k:self.power_state.get(k) for k in ('supported','acquired','error')}}
        if key=='inventory-sku':
            proof['inventory_diagnostics']=result.get('inventory_diagnostics',[])
            for field in ('inventory_execution_mode','execution_tab_id','execution_tab_state','execution_visibility'):
                if field in result:proof[field]=result[field]
        if key=='shop-insights':proof.update(insights_report=scope['report'],request_params=scope['params'])
        if key=='business-stats':proof.update(business_report=scope['report'],request_params=scope['params'])
        if key in ('order-list','order-lookup'):
            proof['order_diagnostics']=result.get('diagnostics',[])
        self.audit.append(proof)
        self.last_response_text=result['text']
        return payload,proof


def capture_api(key,day,store,*,client=None):
    if client is None:
        with APIClient({'platform':'jd','store_key':store}) as active:return capture_api(key,day,store,client=active)
    payload,proof=client.request(key,day)
    text=client.last_response_text
    if not isinstance(text,str) or hashlib.sha256(text.encode()).hexdigest()!=proof['response_sha256']:raise ValueError('接口正文与证据哈希不符')
    return {'text':text,'status':200,'identity':proof['identity'],'source':'registered-api','transport':'registered-api',
      'request_timestamp':proof['request_started_at'],'requested_after':proof['dispatched_at'],
      'timings':{'capture_ms':proof['elapsed_ms']},'api_proof':proof}


def attach_source_dictionary(result,day):
    if (result.get('source_dictionary') or {}).get('text'):return result
    identity=result['identity']
    with APIClient({'platform':'jd','store_key':identity['store_key']}) as client:
        payload,proof=client.request('source-dictionary',day)
    return {**result,'source_dictionary':{'text':json.dumps(payload,ensure_ascii=False),
      'identity_anchor':proof['identity']['identity_anchor'],'source':'registered-api',
      'request_started_at':proof['request_started_at'],'response_sha256':proof['response_sha256']}}

