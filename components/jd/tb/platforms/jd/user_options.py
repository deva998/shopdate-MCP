"""Native UI option contracts traced to the saved official page bundles."""
from copy import deepcopy

PERIODS={
    'visitor':{'sections':('time','profile'),'periods':('week','month')},
    'insight':{'sections':('summary','trend','detail','competitors'),'periods':('week','month','quarter')},
    'newold':{'sections':('summary','trend','profile','brands'),'periods':('week','month')},
    'plus':{'sections':('summary','trend','profile','brands','special','products'),'periods':('week','month')},
    'pots':{'sections':('summary','trend','profile','brands'),'periods':('week','month')},
    'fans-summary':{'sections':('summary','trend','detail','compare-trend'),'periods':('week','month','day7','day30')},
    'fans-feature':{'sections':('profile','detail','brands','channel-behaviour'),'periods':('week','month','day7','day30')},
    'member-feature':{'sections':('profile','detail','brands','trend'),'periods':('week','month','day7','day30')},
}
LIST_REPORTS={'analysis-audience-detail-filtered':'audience-base','analysis-reach-detail-filtered':'reach'}


def extend_contracts(contracts,pages):
    contracts['analysis-insight-page-meta']={'origin':'https://jdsz.jd.com','path':'/sz/api/getPageInfo.ajax','page':pages['insight'],'schema':'fixed-meta','response':'read-metadata','min_extension':'0.9.27'}
    contracts['analysis-insight-competitors']={'origin':'https://szgateway.jd.com','path':'/szpaas/szajax/cust/insight/getFlowIndexCompare.ajax','page':pages['insight'],'schema':'insight-competitors','response':'data','needs_competitor_auth':True,'min_extension':'0.9.27'}
    contracts['analysis-fans-feature-channel-behaviour']={**deepcopy(contracts['analysis-fans-feature-detail']),'schema':'fans-channel-behaviour','min_extension':'0.9.27'}
    for key,c in list(contracts.items()):
        if c['schema']=='member-industry-rank' and not c.get('period'):
            for period in ('day7','day30'):contracts[key+'-'+period]={**deepcopy(c),'period':period,'min_extension':'0.9.27'}
    for module,options in PERIODS.items():
        for section in options['sections']:
            base='analysis-'+module+'-'+section
            for period in options['periods']:
                key=base+'-'+period
                if key in contracts:continue
                c=deepcopy(contracts[base]);c.update(schema='period-get',native_schema=c['schema'],base_report=base,period=period,min_extension='0.9.27')
                c['keep_date_type']=module in ('insight','member-feature') or module=='visitor' and section=='profile'
                if period in ('day7','day30') and module=='member-feature' and section in ('detail','trend'):c['native_date_type']=period
                contracts[key]=c
    for key,native in LIST_REPORTS.items():
        module='audience' if native=='audience-base' else 'reach'
        contracts[key]={**deepcopy(contracts['analysis-'+module+'-detail']),'schema':'list-filter','native_schema':native,'min_extension':'0.9.27','pagination':{'page_size':10,'group_key':['id']}}
    for key,origin,path,page in [
        ('analysis-insight-competitor-options','https://szgateway.jd.com','/szajax/sz/flow/getAllCompeteShopInfo.ajax',pages['insight']),
        ('analysis-reach-options','https://szgateway.jd.com','/szajax/sz/cust/audienceManage/getReachTypeConfig.ajax',pages['reach']),
        ('analysis-member-feature-options','https://jdsz.jd.com','/sz/api/cust/memberFeature/userInfo.ajax',pages['member-feature'])]:
        contracts[key]={'origin':origin,'path':path,'page':page,'schema':'snapshot','response':'read-metadata','min_extension':'0.9.27'}


def list_progress(results,require_complete=False):
    if not results or len(results)>1000:raise ValueError('缺少人群分页或超过页数上限。')
    report=results[0]['section']
    if report not in LIST_REPORTS:raise ValueError('该列表未登记全量分页。')
    seen=set();count=0;total=None;scope={k:v for k,v in results[0]['params'].items() if k!='pageNum'}
    for page,item in enumerate(results,1):
        p=item['params'];data=item['result']['data'];current=data.get('totalNum');rows=data.get('data')
        if item['section']!=report or type(p.get('pageNum')) is not int or p['pageNum']!=page or {k:v for k,v in p.items() if k!='pageNum'}!=scope:raise ValueError('人群分页缺页或范围不符。')
        if type(current) is not int or current<0 or total is not None and current!=total or not isinstance(rows,list):raise ValueError('人群分页总数无效或变化。')
        total=current
        if page>max(1,(total+9)//10) or len(rows)!=min(10,max(0,total-(page-1)*10)):raise ValueError('人群分页行数不符。')
        for row in rows:
            key=row.get('id')
            if type(key) not in (str,int) or not str(key) or str(key) in seen:raise ValueError('人群记录唯一ID缺失或重复，不能认定全量。')
            seen.add(str(key))
        count+=len(rows)
    complete=count==total and len(seen)==total
    if require_complete and not complete:raise ValueError('人群分页尚未取全。')
    return {'complete':complete,'official_total':total,'captured_records':count,'unique_records':len(seen),'missing_records':total-len(seen),'pages':len(results),'page_size':10,'note':'按指定创建日/推送日范围及筛选核对列表；不代表所有历史日期，固定系统推荐列表不参与分页。'}


def list_params(native,day,start_day,page,name,reach_sys,reach_status):
    from .shop_insights import historical_day
    start=start_day or day;historical_day(start)
    if start>day:raise ValueError('人群日期起止顺序无效。')
    if not isinstance(name,str) or name!=name.strip() or len(name)>40 or any(ord(c)<32 for c in name):raise ValueError('人群名称须为去除首尾空白的40字以内文本。')
    p={'audienceName':name,'startDate':start,'endDate':day,'pageNum':page,'pageSize':10}
    if native=='audience-base':
        if reach_sys!=0 or reach_status!=0:raise ValueError('基础人群不接受触达筛选。')
        p['audienceType']=1
    else:
        if type(reach_sys) is not int or type(reach_status) is not int or reach_sys not in (0,1,2) or reach_status not in {0:(0,1,2,3,4,5,6),1:(0,1,2,3),2:(0,4,5,6)}[reach_sys]:raise ValueError('触达系统与状态组合无效。')
        p.update(reachSys=reach_sys,reachStatus=reach_status)
    return p


def check_competitors(meta,options,params):
    if not isinstance(meta,dict) or str(meta.get('SHOP_ID'))!=params.get('selfShopId') or str(meta.get('USER_TYPE'))!='0':raise ValueError('竞店对比的本店身份与官方页面元数据不符。')
    if not isinstance(options,dict) or options.get('isAuth') is not True or not isinstance(options.get('list'),list):raise ValueError('官方未明确授权竞店对比，停止查询。')
    allowed={str(row['id']) for row in options['list'] if isinstance(row,dict) and 'id' in row}
    selected=[params[k] for k in ('compete1ShopId','compete2ShopId') if k in params]
    if len(set(selected))!=len(selected) or any(shop not in allowed or shop==params['selfShopId'] for shop in selected):raise ValueError('竞店不在官方可查列表中或重复。')
    return {'authorized':True,'self_shop_id':params['selfShopId'],'competitor_ids':selected}
