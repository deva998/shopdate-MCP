"""Read-only ad acquisition and pure official-response normalizers."""
from datetime import datetime,timezone
from .evidence import encoded
from .metrics import CN
from copy import deepcopy
import time


def select_plan_scope(rows,source_coverage):
    """Restrict plans to the same three official scenes as channel controls."""
    from .ad_review import total
    codes={'onebpSite','onebpSearch','onebpDisplay'}
    selected=[r for r in rows if r.get('bizCode') in codes or not r.get('bizCode')]
    excluded=[r for r in rows if r.get('bizCode') and r['bizCode'] not in codes]
    unknown=sum(not r.get('bizCode') for r in rows)
    return selected,{'expected_rows':len(selected) if source_coverage.get('complete') else None,
        'retrieved_rows':len(selected),'complete':source_coverage.get('complete') is True and not unknown,
        'scope':'onebpSite/onebpSearch/onebpDisplay','source_coverage':source_coverage,
        'excluded_rows':len(excluded),'excluded_spend':total([{'spend':r.get('charge')} for r in excluded],'spend'),
        'unknown_scope_rows':unknown}


def merge_pages(pages,id_field):
    expected=None;unique={};duplicates=[];raw_count=0
    for response in pages:
        if response.get('info',{}).get('ok') is False:raise ValueError('广告接口业务失败。')
        data=response.get('data',{});count=data.get('count');rows=data.get('list')
        if type(count) is not int or count<0 or not isinstance(rows,list):raise ValueError('广告分页结构异常。')
        if expected is not None and expected!=count:raise ValueError('广告分页官方总数发生变化，请刷新快照。')
        expected=count;raw_count+=len(rows)
        for row in rows:
            identifier=row.get(id_field)
            if not isinstance(identifier,(str,int)) or isinstance(identifier,bool):raise ValueError('广告维度ID缺失或精度不明。')
            identifier=str(identifier)
            if identifier in unique:
                duplicates.append(identifier)
                if encoded(unique[identifier])!=encoded(row):raise ValueError('重复ID的广告指标发生冲突，请刷新快照。')
            else:unique[identifier]=row
    complete=expected is not None and len(unique)==expected and not duplicates
    return list(unique.values()),{'expected_rows':expected,'retrieved_rows':len(unique),
        'raw_rows':raw_count,'duplicate_ids':sorted(set(duplicates)),'complete':complete}


def category_tree(response,day):
    if response.get('code')!=0 or not isinstance(response.get('data'),list):raise ValueError('官方类目销售接口失败。')
    result=[]
    def visit(row,path,names):
        identifier=row.get('cateId');identifier=identifier.get('value') if isinstance(identifier,dict) else identifier
        if not isinstance(identifier,(str,int)) or isinstance(identifier,bool):raise ValueError('官方类目ID缺失。')
        identifier=str(identifier);name=row.get('cateName')
        if not isinstance(name,str) or not name:raise ValueError('官方类目名称缺失。')
        if row.get('parentCateId') not in (None,0,'0') and path and str(row['parentCateId'])!=path[-1]:raise ValueError('官方类目父级不一致。')
        stamp=row.get('statDate',{});stamp=stamp.get('value') if isinstance(stamp,dict) else stamp
        if stamp is not None and datetime.fromtimestamp(stamp/1000,tz=CN).date().isoformat()!=day:raise ValueError('官方类目销售日期不一致。')
        value=row.get('payAmt');value=value.get('value') if isinstance(value,dict) else value
        result.append({'id':identifier,'path':path+[identifier],'names':names+[name],'sales':value})
        for child in row.get('children') or []:visit(child,path+[identifier],names+[name])
    for row in response['data']:visit(row,[],[])
    if len({r['id'] for r in result})!=len(result):raise ValueError('官方类目销售有重复ID。')
    return result


def acquire(provider,store,day,*,state=None,save=lambda state:None,category_limit=20,category_seed=None):
    """Checkpointed registered reads; provider owns transport/auth and bridge release."""
    from .source import verify_symc_identity
    from .metrics import window,numeric
    window('symc',store,day,'daily')
    if type(category_limit) is not int or not 0<=category_limit<=100:raise ValueError('每批官方类目查询数应为0至100。')
    mode=getattr(provider,'attribution_mode','realtime')
    plan_order=getattr(provider,'plan_order','charge')
    state=deepcopy(state) if state else {'platform':'symc','store_key':store,'date':day,
        'source_contract':'ad_live_v1','raw':{'channels':{},'item_pages':[],'plan_pages':[]},
        'mappings':{},'attribution_mode':mode,'plan_order':plan_order,
        'acquired_at':datetime.now(timezone.utc).isoformat()}
    if state.get('source_contract')!='ad_live_v1' or state.get('store_key')!=store or state.get('date')!=day or state.get('platform')!='symc':
        raise ValueError('广告续跑来源、店铺、日期或口径不一致。')
    if state.get('attribution_mode','realtime')!=mode:
        raise ValueError('续跑归因口径不同；请使用refresh重新采集，禁止混用实时与历史归因。')
    if state.get('plan_order','charge')!=plan_order and state['raw'].get('plan_pages'):
        raise ValueError('续跑计划分页排序不同；请使用refresh重新采集，禁止拼接不同排序的分页。')
    state['plan_order']=plan_order
    raw=state['raw']
    phase_started=time.perf_counter()
    phases={}
    def phase(name):
        nonlocal phase_started
        now=time.perf_counter();phases[name]=round((now-phase_started)*1000);phase_started=now
    def checked_save():
        verify_symc_identity(provider.identity(),store)
        state['identity_checked_at']=datetime.now(timezone.utc).isoformat()
        save(state)
    def paged(kind,id_field):
        pages=raw[kind+'_pages']
        if pages:
            _,quality=merge_pages(pages,id_field)
            if quality['duplicate_ids']:raise ValueError('广告分页存在重复ID，请刷新快照；已停止追加分页。')
            if sum(len(p['data']['list']) for p in pages)>=quality['expected_rows'] or not pages[-1]['data']['list']:
                rows,quality=merge_pages(pages,id_field)
                if not quality['complete']:raise ValueError('广告分页不完整或存在重复ID，请刷新快照；已停止后续类目查询。')
                return rows,quality
        while len(pages)<200:
            response=provider.page(kind,day,len(pages)*100)
            _,quality=merge_pages([*pages,response],id_field)
            verify_symc_identity(provider.identity(),store)
            pages.append(response);save(state)
            if quality['duplicate_ids']:raise ValueError('广告分页存在重复ID，请刷新快照；已停止追加分页。')
            if not response['data']['list'] or sum(len(p['data']['list']) for p in pages)>=response['data']['count']:break
        rows,quality=merge_pages(pages,id_field)
        if not quality['complete']:raise ValueError('广告分页不完整或存在重复ID，请刷新快照；已停止后续类目查询。')
        return rows,quality
    try:
        verify_symc_identity(provider.identity(),store)
        provider.switch('alimama')
        for scene in ('wholesite','keyword','crowd'):
            if scene not in raw['channels']:
                response=provider.scene(scene,day)
                if response.get('info',{}).get('ok') is False or not isinstance(response.get('data',{}).get('list'),list) or len(response['data']['list'])!=1:
                    raise ValueError('广告渠道汇总结构异常。')
                verify_symc_identity(provider.identity(),store)
                raw['channels'][scene]=response;save(state)
        phase('channel_ms')
        item_rows,item_coverage=paged('item','promotionId')
        phase('item_pages_ms')
        plan_rows,plan_coverage=paged('plan','campaignId')
        plan_rows,plan_coverage=select_plan_scope(plan_rows,plan_coverage)
        phase('plan_pages_ms')
        provider.switch('sycm')
        if 'sales' not in raw:
            sales=provider.sales(day)
            category_tree(sales['categories'],day)
            verify_symc_identity(provider.identity(),store)
            raw['sales']=sales;save(state)
        phase('sales_ms')
        categories=category_tree(raw['sales']['categories'],day)
        roots={r['names'][0]:r['id'] for r in categories if len(r['path'])==1}
        if category_seed:
            if category_seed.get('platform')!='symc' or category_seed.get('store_key')!=store:raise ValueError('官方类目缓存店铺不符。')
            for item in category_seed.get('items',[]):
                if item.get('category_id') and item.get('official_path') and item['id'] not in state['mappings']:
                    state['mappings'][item['id']]={'cateId':item['category_id'],'path':item['official_path'],
                        'observed_at':item.get('category_observed_at') or category_seed.get('provenance',{}).get('category_observed_at'),
                        'source':'explicit_official_category_evidence','reused':True}
        required=[r for r in item_rows if str(r['promotionId']).isdigit() and
                  any((numeric(r.get(f)) or 0)!=0 for f in ('charge','click','alipayInshopAmt'))]
        pending=[str(r['promotionId']) for r in required if str(r['promotionId']) not in state['mappings']]
        category_queries=0
        for identifier in pending[:category_limit]:
            info=provider.price(identifier)
            category_queries+=1
            verify_symc_identity(provider.identity(),store)
            state['mappings'][identifier]={'cateId':info.get('cateId'),
                'path':str(info.get('cateName') or '').replace('&gt;','>').split('>') if info.get('cateName') else [],
                'observed_at':datetime.now(timezone.utc).isoformat(),
                'source':'/cc/item/price/info.json','reused':False}
            save(state)
        pending=[identifier for identifier in pending if identifier not in state['mappings']]
        phase('category_ms')
        def convert(row,identifier,name):
            return {'id':str(identifier),'name':name,'spend':row.get('charge'),'attributed_sales':row.get('alipayInshopAmt'),
                'clicks':row.get('click'),'conversions':row.get('alipayInshopNum'),'impressions':row.get('adPv')}
        items=[]
        for row in item_rows:
            identifier=str(row['promotionId']);mapping=state['mappings'].get(identifier,{})
            item=convert(row,identifier,row.get('promotionName',identifier))
            path=mapping.get('path',[])
            item.update(category_id=str(mapping['cateId']) if mapping.get('cateId') is not None else None,
                official_path=path,category_root_id=roots.get(path[0]) if path else None,
                category_mapping_source='/cc/item/price/info.json' if path else None,
                category_observed_at=mapping.get('observed_at'),category_mapping_reused=mapping.get('reused',False))
            items.append(item)
        channels=[convert(response['data']['list'][0],key,key) for key,response in raw['channels'].items()]
        from .ad_review import total
        overview=raw['sales']['overview'].get(day,{})
        sales=overview.get('payAmt');sales=sales.get('value') if isinstance(sales,dict) else sales
        checked_save()
        return {'platform':'symc','store_key':store,'date':day,'identity_verified':True,'identity_status':'verified',
            'attribution':{'window_days':15,'mode':mode,'maturity':'observed_snapshot','conversion_definition':'alipayInshopNum/click'},
            'controls':{'spend':total(channels,'spend'),'store_sales':sales},
            'channels':channels,'items':items,'plans':[convert(row,row['campaignId'],row.get('campaignName',str(row['campaignId']))) for row in plan_rows],
            'categories':categories,'item_coverage':{**item_coverage,'scope':'all_items'},'plan_coverage':plan_coverage,
            'pending_category_ids':pending,'acquisition_state':state,
            'provenance':{'type':'registered_live_queries','acquired_at':state['acquired_at'],
                'phase_timings_ms':phases,'category_queries_this_call':category_queries,
                'category_evidence_policy':'explicit cache retains original observation time; uncached facts queried live',
                'reused_category_items':sum(bool(m.get('reused')) for m in state['mappings'].values())}}
    finally:
        provider.close()
