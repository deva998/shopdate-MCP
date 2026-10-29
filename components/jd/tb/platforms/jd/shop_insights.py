"""Official category and customer overview reads, with explicit time scopes."""
import argparse
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlencode
from uuid import uuid4
from .user_analysis import CONTRACTS as ANALYSIS_CONTRACTS

HOST='https://szgateway.jd.com'
CATEGORY_PAGE='https://jdsz.jd.com/szweb/view/product/category-analyze-temp.html'
USER_PAGE='https://jdsz.jd.com/szweb/view/customer/cust-summarys-temp.html'
ROUTES={
    'category-summary':('/szpaas/szajax/category/getOfflineCategorySummary.ajax',CATEGORY_PAGE),
    'category-trend':('/szpaas/szajax/category/getOfflineCategoryTrend.ajax',CATEGORY_PAGE),
    **{'user-'+key:('/szajax/sz/cust/growthSummary/'+path+'.ajax',USER_PAGE) for key,path in {
        'dates':'dateRange','assets':'shopAsset','summary':'summary','diagnosis':'diagnosis',
        'trend':'trend','conversion':'conversionEffect','products':'shopGoodsList'}.items()}}
ROUTES.update({key:(spec['path'],spec['page']) for key,spec in ANALYSIS_CONTRACTS.items()})
COMMANDS=['category-analysis','category-trend','user-overview','user-detail','user-modules','user-analysis']


def historical_day(day):
    if not isinstance(day,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',day) or date.fromisoformat(day).isoformat()!=day:
        raise ValueError('日期必须为YYYY-MM-DD。')
    if day>=datetime.now(timezone(timedelta(hours=8))).date().isoformat():raise ValueError('仅允许完整历史日。')
    return day


def build(report,day,*,category_type='industry',second_id=None,third_id=None,audience=None,target=3):
    historical_day(day)
    if report not in ROUTES:raise ValueError('未登记的类目或用户只读接口。')
    if category_type not in ('industry','shop'):raise ValueError('类目类型必须为industry或shop。')
    if type(target) is not int or target not in (1,2,3):raise ValueError('比较目标必须为1/2/3。')
    path,page=ROUTES[report]
    if report.startswith('category-'):
        params={'dateType':'day','date':day,'startDate':day,'endDate':day,'categoryType':1 if category_type=='industry' else 0}
        if report=='category-trend':
            if category_type=='shop' and third_id is None:raise ValueError('店铺趋势必须传入汇总行的官方三级ID；上级汇总行也须照原值传入，例如999999，不能省略为空。')
            if not isinstance(second_id,str) or not re.fullmatch(r'\d+',second_id):raise ValueError('趋势必须指定已核验的官方二级类目ID。')
            if third_id is not None and (not isinstance(third_id,str) or not re.fullmatch(r'\d+',third_id)):raise ValueError('三级类目ID无效。')
            params.update(secondIndId=second_id,thirdIndId=third_id or '')
    elif report=='user-dates':params={}
    else:
        params={'startDate':(date.fromisoformat(day)-timedelta(days=29)).isoformat(),'endDate':day}
        if report=='user-assets':
            if audience not in ('all','potential','new','old'):raise ValueError('资产类型必须为all/potential/new/old。')
            params.update(startDate=day,assetsCustType=audience)
        if report in ('user-trend','user-conversion','user-products'):
            if audience not in ('new','old','fans','member'):raise ValueError('运营类型必须为new/old/fans/member。')
            params['custType']=audience
            if report in ('user-conversion','user-products'):params['target']=target
    return {'method':'GET','path':path,'page':page,'url':HOST+path},params


def validate_params(report,params):
    if not isinstance(params,dict) or report not in ROUTES:raise ValueError('未登记的查询。')
    if report in ANALYSIS_CONTRACTS:
        from .user_analysis import validate_params as validate_analysis
        return validate_analysis(report,params)
    if report=='user-dates':
        if params:raise ValueError('用户可用日期接口不接受筛选参数。')
        return params
    if report.startswith('category-') and type(params.get('categoryType')) is not int:raise ValueError('类目类型必须为整数0/1。')
    day=params.get('endDate')
    _,expected=build(report,day,category_type={0:'shop',1:'industry'}.get(params.get('categoryType'),'industry'),
        second_id=params.get('secondIndId'),third_id=params.get('thirdIndId') or None,
        audience=params.get('assetsCustType') if report=='user-assets' else params.get('custType'),target=params.get('target',3))
    if params!=expected:raise ValueError('请求参数超出已核实的单日/近30天只读范围。')
    return params


def make_url(report,params):
    validate_params(report,params)
    origin=ANALYSIS_CONTRACTS[report]['origin'] if report in ANALYSIS_CONTRACTS else HOST
    is_post=ANALYSIS_CONTRACTS.get(report,{}).get('method')=='POST'
    return origin+ROUTES[report][0]+('?' + urlencode(sorted((k,str(v).lower() if type(v) is bool else v) for k,v in params.items())) if params and not is_post else '')


def business_body(payload):
    if not isinstance(payload,dict):raise ValueError('响应不是对象。')
    errors=payload.get('errors')
    if errors is not None and (not isinstance(errors,list) or errors):raise ValueError('官方返回错误字段，不能作为空表。')
    if 'status' in payload:
        if type(payload['status']) not in (str,int) or str(payload['status'])!='0':raise ValueError('官方业务状态失败，不能作为空表。')
        return payload
    header=payload.get('header')
    if not isinstance(header,dict) or type(header.get('code')) not in (str,int) or str(header['code'])!='0' or payload.get('errors'):
        raise ValueError('缺少成功业务状态，不能作为空表。')
    body=payload.get('body')
    if not isinstance(body,dict):raise ValueError('缺少官方响应body。')
    if 'status' in body and str(body['status'])!='0':raise ValueError('官方body业务状态失败。')
    return body


def normalize(payload,report):
    if report not in ROUTES:raise ValueError('未登记的响应类型。')
    if ANALYSIS_CONTRACTS.get(report,{}).get('response')=='oneservice':
        from .user_metrics import parse
        return parse(payload,report)
    body=business_body(payload)
    if report in ANALYSIS_CONTRACTS:
        kind=ANALYSIS_CONTRACTS[report]['response']
        if kind=='content':
            if 'content' not in body or not isinstance(body['content'],(dict,list)):raise ValueError('缺少官方用户统计content。')
            data=deepcopy(body['content'])
        elif kind=='read-metadata':
            data=deepcopy(body.get('content',body))
            if not isinstance(data,(dict,list)):raise ValueError('只读元数据结构无效。')
        elif kind=='series':
            # Legacy response status=0/content and new header=0/body are both official wrappers.
            source=body['content'] if 'content' in body else body
            if not isinstance(source,dict) or not isinstance(source.get('categories'),list) or not isinstance(source.get('series'),list):raise ValueError('缺少官方访客时段序列。')
            data=deepcopy(source)
        elif kind=='object-data':
            if not isinstance(body.get('data'),dict):raise ValueError('缺少官方用户分析data对象。')
            data=deepcopy(body)
        else:
            if not isinstance(body.get('data'),list):raise ValueError('缺少官方用户分析data列表。')
            data=deepcopy(body)
        coverage={'scope':'official_user_analysis_returned_data','nulls_preserved':True,
            'all_store_catalog_complete':False,'note':ANALYSIS_CONTRACTS[report].get('metric_note','保留原始指标；列表范围不代表全店/全平台全集。')}
        if report.endswith('-trend'):
            values=data.get('categories',[]) if isinstance(data,dict) else []
            if not values and isinstance(data,dict) and isinstance(data.get('data'),list):values=[row.get(ANALYSIS_CONTRACTS[report].get('date_field','DateTime')) for row in data['data'] if isinstance(row,dict)]
            times=[]
            for value in values:
                if type(value) is int:value=str(value)
                if not isinstance(value,str) or not re.fullmatch(r'\d{8}|\d{4}-\d{2}-\d{2}',value):raise ValueError('用户趋势日期字段无效。')
                times.append(datetime.strptime(value,'%Y%m%d' if len(value)==8 else '%Y-%m-%d').date())
            coverage.update(returned_start=min(times).isoformat() if times else None,returned_end=max(times).isoformat() if times else None,
                unique_dates=len(set(times)),duplicate_dates=len(times)-len(set(times)),missing_days_within_span=(max(times)-min(times)).days+1-len(set(times)) if times else None)
        schema=ANALYSIS_CONTRACTS[report].get('native_schema',ANALYSIS_CONTRACTS[report]['schema'])
        if schema in ('audience-base','audience-system','reach'):
            if not isinstance(data,dict) or not isinstance(data.get('data'),list) or type(data.get('totalNum')) is not int or data['totalNum']<0:raise ValueError('缺少有效的官方分页列表或总数。')
            if len(data['data'])>10:raise ValueError('官方分页返回超出登记页容量。')
            coverage.update(pagination='server_pages_10',official_total=data.get('totalNum'),returned_rows=len(data['data']),whole_query_complete=False)
            if schema=='audience-system':coverage.update(pagination='not_applicable_fixed_current_list',note='官方忽略翻页；固定当前系统推荐列表，不作为历史数据或新增页面。')
        return {'data':data,'coverage':coverage}
    if report.startswith('category-'):
        rows=body.get('data')
        if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):raise ValueError('缺少官方类目列表。')
        def descendants(nodes):
            count=0
            for row in nodes:
                child=row.get('children')
                if child is not None:
                    if not isinstance(child,list) or any(not isinstance(v,dict) for v in child):raise ValueError('下级类目结构无效。')
                    count+=len(child)+descendants(child)
            return count
        coverage={'scope':'official_returned_category_tree' if report=='category-summary' else 'official_returned_trend',
            'root_rows':len(rows),'descendant_rows':descendants(rows),'pagination':'frontend_local_slicing',
            'all_store_catalog_complete':False,'nulls_preserved':True}
        if report=='category-trend':
            times=[]
            for row in rows:
                value=row.get('TIME')
                if not isinstance(value,str) or not re.fullmatch(r'\d{8}',value):raise ValueError('趋势缺少官方TIME字段。')
                times.append(datetime.strptime(value,'%Y%m%d').date())
            coverage.update(pagination='not_applicable',returned_start=min(times).isoformat() if times else None,
                returned_end=max(times).isoformat() if times else None,unique_dates=len(set(times)),
                duplicate_dates=len(times)-len(set(times)),missing_days_within_span=(max(times)-min(times)).days+1-len(set(times)) if times else None,
                note='请求为单日锚点，序列范围按官方TIME字段披露，不当成单日数据。')
        return {'rows':deepcopy(rows),'coverage':coverage}
    if 'content' not in body or not isinstance(body['content'],(dict,list)):raise ValueError('缺少官方用户统计content。')
    return {'data':deepcopy(body['content']),'coverage':{'scope':'official_customer_aggregate','nulls_preserved':True}}


def check_available(payload,day):
    historical_day(day);data=normalize(payload,'user-dates')['data']
    if not isinstance(data,dict):raise ValueError('官方可用日期结构错误。')
    def as_day(value):
        if isinstance(value,int):return datetime.fromtimestamp(value/1000,timezone(timedelta(hours=8))).date().isoformat()
        if isinstance(value,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:[ T].*)?',value):
            return date.fromisoformat(value[:10]).isoformat()
        raise ValueError('官方可用日期无效。')
    begin,end=as_day(data.get('startDate')),as_day(data.get('endDate'))
    if not begin<=day<=end:raise ValueError('日期不在用户模块官方可用范围：'+begin+' 至 '+end+'。')
    return {'available_start':begin,'available_end':end}


def verify_record(record,report,params,day,store):
    from ...core.stores import verify_identity
    proof=record.get('proof',{});verify_identity({'platform':'jd','store_key':store},proof.get('identity'))
    validate_params(report,params)
    if proof.get('case')!='shop-insights' or proof.get('date')!=day or proof.get('insights_report')!=report or proof.get('request_params')!=params:
        raise ValueError('类目/用户证据请求范围不符。')
    if ANALYSIS_CONTRACTS.get(report,{}).get('method')=='POST':
        from .user_metrics import validate_body
        validate_body(report,params,proof.get('request_body'))
    raw=record.get('response_text')
    if not isinstance(raw,str) or hashlib.sha256(raw.encode()).hexdigest()!=proof.get('response_sha256'):
        raise ValueError('类目/用户原始响应哈希不符。')
    payload=json.loads(raw);result=normalize(payload,report)
    if ANALYSIS_CONTRACTS.get(report,{}).get('window_days'):
        coverage=result['coverage']
        if coverage.get('returned_start') and (coverage['returned_start']<params['startDate'] or coverage['returned_end']>params['endDate']):raise ValueError('会员/权益趋势返回超出已登记日期范围。')
    if report=='category-trend' and result['rows'] and result['coverage']['returned_end']!=day:
        raise ValueError('趋势返回末日与请求锚点不符。')
    if report.startswith('category-'):
        def check_shop(rows):
            for row in rows:
                if 'SHOP' in row and str(row['SHOP'])!=store.removeprefix('jd:mall:'):raise ValueError('类目响应店铺不符。')
                check_shop(row.get('children') or [])
        check_shop(result['rows'])
    return payload


def verify_specs(command,specs,day,query_options=None):
    if not isinstance(specs,list) or not specs:raise ValueError('缺少数据段定义。')
    for spec in specs:
        if not isinstance(spec,(list,tuple)) or len(spec)!=2:raise ValueError('数据段定义无效。')
        key,params=spec;validate_params(key,params)
        if key!='user-dates' and ANALYSIS_CONTRACTS.get(key,{}).get('schema') not in ('snapshot','fixed-meta','audience-system','member-industry-categories') and params['endDate']!=day:raise ValueError('数据段日期不符。')
    keys=[v[0] for v in specs]
    if command=='user-analysis':
        from .user_analysis import specs as analysis_specs
        if not isinstance(query_options,dict):raise ValueError('缺少用户分析查询定义。')
        expected_specs=analysis_specs(day=day,**query_options)
        if query_options.get('all_pages'):
            if len(expected_specs)!=1 or not ANALYSIS_CONTRACTS[expected_specs[0][0]].get('pagination') or not 1<=len(specs)<=1000:raise ValueError('全量分页范围无效。')
            key,params=expected_specs[0]
            expected_specs=[(key,{**params,'pageNum':page}) for page in range(1,len(specs)+1)]
        if [list(v) for v in specs]!=[list(v) for v in expected_specs]:raise ValueError('用户分析数据段缺失、重复或筛选不符。')
        return
    expected={'category-analysis':['category-summary'],'category-trend':['category-trend'],
        'user-overview':['user-dates']+['user-assets']*4+['user-summary','user-diagnosis']}
    if command=='user-detail':
        if len(keys)!=2 or keys[0]!='user-dates' or keys[1] not in ('user-trend','user-conversion','user-products'):raise ValueError('用户下钻数据段不符。')
    elif keys!=expected.get(command):raise ValueError('查询命令与数据段不符。')
    if command=='user-overview' and [p['assetsCustType'] for _,p in specs[1:5]]!=['all','potential','new','old']:
        raise ValueError('用户资产数据段不完整或重复。')


def modules():
    live={'用户概况','访客分析','用户洞察','新老客分析','Plus会员概况','未购访客分析','关注店铺用户概况','关注店铺用户特征','关注店铺用户质量','品牌会员特征','品牌会员概况','会员权益效果','人群列表','触达记录','定向人群营销效果'}
    partial={'关注店铺用户特征','品牌会员特征','品牌会员概况','会员权益效果','人群列表','触达记录'}
    pending=set()
    notes={'未购访客分析':'汇总、趋势、画像及指定官方类目的品牌偏好已核验',
        '关注店铺用户概况':'汇总、趋势、成交类型对比及关注客户对比弹窗30日趋势已核验；日期范围认实际返回',
        '关注店铺用户特征':'周亲密度1至4档的画像、渠道和指定官方类目品牌偏好已实测；先查官方近三周可用窗口，不支持超范围亲密度或自定义区间。非默认客群与类目的全部组合未遍历',
        '品牌会员特征':'全部/开卡画像、成交品牌偏好及入会渠道已核验；原生周/月/自定义画像、渠道及成交品牌偏好已在线。子渠道30日趋势另列；并非每个筛选组合均实测',
        '品牌会员概况':'整体/开卡/运营、新老/对比/等级、三类积分、三类权益、SKU/SPU Top10均已核验日/周/月/自定义；新增新老客逐序列及对比31天趋势完整。五种本店行业排名已在线，权限与二三级类目先验；不等于行业全店榜Top10已接入。其他非默认组合不作全部验收承诺',
        '会员权益效果':'5种权益及综合汇总、7天趋势、质量、明细及权益对比已在线；周/月/自定义默认95折质量/明细、综合SPU和对比亦已核验。2000/2003警告保持partial。综合SKU单日1441组、10月19至25日周/自定义8578组、9月12269组已全量；新模式按连续唯一分组与官方成功空页核验，不将满页size当固定总数；其他权益类型明细组合未全部遍历',
        '购物车营销效果':'用户2026-10-27指示暂标no_data，停止自动尝试；不推断永久不适用或无权限，等待后续明确指令',
        '人群列表':'基础人群为指定创建日、指定页；当前系统推荐为固定列表，官方忽略翻页；不代表全历史全量',
        '触达记录':'指定推送日、指定页已核验；不代表全历史全量，不推送人群',
        '定向人群营销效果':'官方当前效果快照已核验，窗口认effect日期；历史指定日不适用',
        '关注店铺用户质量':'只核验当前质量快照，历史查询不适用，时间以updateTime为准'}
    names=['用户概况','用户洞察','人群列表','触达记录','访客分析','未购访客分析','新老客分析',
        '关注店铺用户概况','关注店铺用户特征','关注店铺用户质量','Plus会员概况','会员权益效果',
        '品牌会员概况','品牌会员特征','购物车营销效果','定向人群营销效果']
    return {'scope_confirmed_on':'2026-10-27','scope':'全部只读统计，不创建人群、不推送、不配置营销',
            'modules':[{'name':name,'implementation':'no_data' if name=='购物车营销效果' else 'partial_implemented' if name in partial else 'implemented' if name in live else 'partial_implemented_pending_live' if name in pending else 'not_integrated',
            'live_verified':name in live,'commands':['user-overview','user-detail'] if name=='用户概况' else ['user-analysis'] if name in pending|live else [],
            'remaining':notes.get(name,'已核验默认单日请求及真实返回趋势窗口；其他周期与非默认筛选未全验收' if name in live else '官方实际请求模板及在线验收待补，需原生页面样本，不能猜测低代码查询')} for name in names]}

def report_limitations(command,query_options=None):
    common=['空值不补零，转化行为集合不强制作为严格漏斗。','各用户子模块的接入及验收状态须单独查能力目录。']
    if command=='user-analysis' and (query_options or {}).get('module')=='fans-quality':
        return ['关注用户质量为当前快照，业务日期以官方updateTime为准；顶层date仅作证据归档日期，不表示历史日数据。']+common
    if command=='user-analysis' and (query_options or {}).get('module')=='target-marketing':
        return ['营销分析为官方当前快照，统计窗口以effect.startDate/endDate为准；顶层date仅作证据归档，不表示单日。']+common
    if command=='user-analysis' and (query_options or {}).get('section')=='channels-meta':
        return ['入会渠道字典是当前元数据，顶层date仅作证据归档，不表示该历史日统计。']+common
    if command=='user-analysis' and (query_options or {}).get('module') in ('member-overview','benefits') and 'trend' in (query_options or {}).get('section',''):
        return ['按官方默认窗口固定请求：品牌会员回看30天含截止日共31天，权益回看6天含截止日共7天；实际覆盖仍认返回日期，缺失日不补零。']+common
    if command=='user-analysis' and (query_options or {}).get('module') in ('audience','reach'):
        return ['基础人群/触达每次返回指定页10条，不能当全量；用page逐页读取并核对官方totalNum。系统推荐人群为固定当前列表，不按历史日期筛选、官方忽略翻页。','基础人群按创建日期、触达按推送日期筛选；均仅读取，不创建/删除/推送。']+common
    if command=='user-analysis':
        period={'day':'单日'}.get((query_options or {}).get('period','day'),(query_options or {}).get('period'))
        return ['按官方原生'+period+'口径请求；周/月仅完整自然周期，自定义最多31天，不累加日去重指标。趋势实际范围认返回数据。','画像及品牌偏好为官方聚合统计；榜单和商品表可能有官方数量上限，不代表全店商品全集。']+common
    if command.startswith('category-'):
        return ['类目汇总按所选日请求；趋势实际返回窗口见coverage。店铺类目可能重叠，不能简单加总代替全店去重指标。']+common
    return ['消费者资产为所选日快照；用户运营数据为截止所选日近30天，不能当单日数据或跨日累计。']+common


def main(argv):
    from shopdate_workflows.evidence import read_evidence,write_evidence,save_json
    parser=argparse.ArgumentParser(description='京东类目与用户只读统计。单日、实际趋势窗口及当前快照分别标明，保留官方原值。',allow_abbrev=False)
    parser.add_argument('command',choices=COMMANDS)
    parser.add_argument('--store');parser.add_argument('--date')
    parser.add_argument('--category-type',choices=['industry','shop'],default='industry')
    parser.add_argument('--second-id');parser.add_argument('--third-id')
    metric_sections=[key.removeprefix('analysis-member-overview-').removeprefix('analysis-benefits-') for key in ANALYSIS_CONTRACTS if key.startswith(('analysis-member-overview-','analysis-benefits-'))]
    metric_sections+=['intimacy-dates','detail-filtered','options','competitor-options','page-meta','competitors','channel-behaviour']
    parser.add_argument('--section',choices=sorted(set(['overview','summary','trend','conversion','products','profile','time','detail','special','brands','compare-trend','channels-meta','card','operable']+metric_sections)),default='trend')
    parser.add_argument('--audience',choices=['new','old','fans','member'],default='new')
    parser.add_argument('--target',type=int,choices=[1,2,3],default=3)
    from .user_analysis import PAGES
    parser.add_argument('--module',choices=list(PAGES))
    parser.add_argument('--channel',choices=['all','app','pc','wx','sq','m'],default='all')
    parser.add_argument('--feature',choices=['gender','ageSegment','provinceName','cityName','vipLevel','purchasePower','promotionSensitivity'])
    parser.add_argument('--compare',choices=['hb','tb'],default='tb')
    parser.add_argument('--segment',choices=['all','new','old','plus','normal','card','deal','fans','nonfans'])
    parser.add_argument('--first-channel-id');parser.add_argument('--second-channel-id')
    parser.add_argument('--rights-type',choices=['2','3','4','5','6'],default='2',help='PLUS商品权益：2=95折，3=专享券，4=专享赠，5=专享价，6=专享立减')
    parser.add_argument('--page',type=int,default=1)
    parser.add_argument('--all-pages',action='store_true',help='仅登记的分页指标表：抓取至末页并核验官方总数与唯一分组')
    parser.add_argument('--period',choices=['day','week','month','quarter','day7','day30','custom'],default='day')
    parser.add_argument('--audience-name',default='')
    parser.add_argument('--reach-sys',type=int,choices=[0,1,2],default=0)
    parser.add_argument('--reach-status',type=int,choices=list(range(7)),default=0)
    parser.add_argument('--behaviour',choices=['all','follow-day','other-day'],default='all')
    for field in ('self-shop-id','compete1-shop-id','compete2-shop-id'):parser.add_argument('--'+field)
    parser.add_argument('--start-date',help='自定义区间起始日；自然周/月自动计算')
    parser.add_argument('--intimacy',choices=['all','1','2','3','4'],default='all',help='1真爱/2铁杆/3优质小白/4低质小白，仅官方近三周周口径')
    parser.add_argument('--evidence',help='仅离线重放本命令证据，不访问平台')
    args=parser.parse_args(argv)
    try:
        if args.command=='user-modules':
            if any(x.startswith('--') and x.split('=',1)[0]!='--store' for x in argv[1:]):raise ValueError('user-modules仅接受MCP传入的store，不接受数据筛选或证据参数。')
            if args.store is not None and not re.fullmatch(r'jd:mall:\d+',args.store):raise ValueError('必须指定精确京东store_key。')
            print(json.dumps(modules(),ensure_ascii=False));return 0
        historical_day(args.date)
        if not isinstance(args.store,str) or not re.fullmatch(r'jd:mall:\d+',args.store):raise ValueError('必须指定精确京东store_key。')
        explicit={x.split('=',1)[0] for x in argv}
        filters={'--category-type','--second-id','--third-id','--section','--audience','--target','--module','--channel','--feature','--compare','--segment','--page','--all-pages','--first-channel-id','--second-channel-id','--rights-type','--period','--start-date','--intimacy','--audience-name','--reach-sys','--reach-status','--behaviour'}
        filters.update({'--self-shop-id','--compete1-shop-id','--compete2-shop-id'})
        if args.evidence and explicit&filters:raise ValueError('证据重放不能同时指定新筛选参数。')
        allowed=({'--category-type'} if args.command=='category-analysis' else {'--category-type','--second-id','--third-id'} if args.command=='category-trend' else {'--section','--audience','--target'} if args.command=='user-detail' else filters-{'--category-type','--audience','--target'} if args.command=='user-analysis' else set())
        if (explicit&filters)-allowed:raise ValueError('该命令不接受所提供的筛选参数。')
        if args.command=='user-detail' and args.section=='trend' and '--target' in explicit:
            raise ValueError('运营趋势不接受target；比较目标仅适用于conversion/products。')
        if args.command=='user-detail' and args.section not in ('trend','conversion','products'):raise ValueError('用户概况下钻数据段无效。')
        query_options=None
        if args.command=='user-analysis' and not args.evidence:
            section=args.section if '--section' in explicit else 'overview'
            if not args.module:raise ValueError('user-analysis必须指定module。')
            from .user_options import PERIODS
            if '--period' in explicit and args.module not in set(PERIODS)|{'visitors','member-overview','benefits'}:raise ValueError('该子模块尚未登记跨周期查询。')
            if args.start_date is not None and args.period!='custom' and args.module not in ('audience','reach'):raise ValueError('start-date仅用于custom周期或人群/触达日期范围。')
            if '--intimacy' in explicit and args.module!='fans-feature' or args.intimacy!='all' and args.period!='week':raise ValueError('亲密度仅用于关注用户的完整自然周统计。')
            if args.module=='benefits' and section=='comprehensive-products-sku' and (args.all_pages or '--page' in explicit):section+='-full-pages'
            metric_paged=args.module=='benefits' and section in ('comprehensive-products-sku-pages','comprehensive-products-sku-full-pages')
            if args.module in ('audience','reach') and section in ('overview','detail','detail-filtered') and (args.all_pages or args.start_date or explicit&{'--audience-name','--reach-sys','--reach-status'}):section='detail-filtered'
            list_paged=args.module in ('audience','reach') and section=='detail-filtered'
            if args.all_pages and (not (metric_paged or list_paged) or '--page' in explicit):raise ValueError('all-pages仅用于登记分页表，不能同时指定page。')
            if explicit&{'--audience-name','--reach-sys','--reach-status'} and not list_paged:raise ValueError('人群筛选仅用于登记人群/触达列表。')
            if args.module=='audience' and explicit&{'--reach-sys','--reach-status'}:raise ValueError('基础人群不接受触达筛选。')
            if '--behaviour' in explicit and not (args.module=='fans-feature' and section=='channel-behaviour'):raise ValueError('behaviour仅用于关注渠道行为。')
            if explicit&{'--self-shop-id','--compete1-shop-id','--compete2-shop-id'} and not (args.module=='insight' and section=='competitors'):raise ValueError('本店和竞店ID仅用于洞察竞店对比。')
            allowed_extra=set()
            industry=ANALYSIS_CONTRACTS.get('analysis-'+args.module+'-'+section+('' if args.period=='day' else '-'+args.period),{}).get('needs_industry_auth',False)
            if industry:allowed_extra={'--second-id','--third-id'}
            if args.module=='visitors':allowed_extra={'--channel','--feature'}
            elif args.module=='insight' and section!='trend':allowed_extra={'--compare'}
            elif args.module in ('newold','plus') and section in ('overview','profile','brands'):allowed_extra={'--segment','--third-id'}
            elif args.module=='pots' and section=='brands':allowed_extra={'--third-id'}
            elif args.module in ('fans-feature','member-feature') and section in ('profile','brands'):allowed_extra={'--segment'}|({'--third-id'} if section=='brands' else set())
            elif args.module=='fans-summary' and section=='compare-trend':allowed_extra={'--segment'}
            elif args.module=='member-feature' and section in ('detail','trend'):allowed_extra={'--first-channel-id'}|({'--second-channel-id'} if section=='trend' else set())
            elif args.module=='benefits' and section in ('overview','summary','trend','quality','products','products-sku'):allowed_extra={'--rights-type'}
            if (explicit&{'--channel','--feature','--compare','--segment','--second-id','--third-id','--first-channel-id','--second-channel-id','--rights-type'})-allowed_extra:raise ValueError('该用户分析数据段不接受所提供的筛选。')
            if args.feature and section not in ('overview','profile'):raise ValueError('feature仅用于访客画像。')
            if args.third_id and section!='brands' and not industry:raise ValueError('third-id仅用于品牌偏好或登记行业排名。')
            if '--page' in explicit and args.module not in ('audience','reach') and not metric_paged:raise ValueError('page仅用于人群/触达及登记分页表。')
            if '--page' in explicit and args.module=='audience' and section=='special':raise ValueError('系统推荐人群为固定当前列表，不接受page。')
            query_options={'module':args.module,'section':section,'channel':args.channel,'feature':args.feature,'compare':args.compare,'segment':args.segment,'third_id':args.third_id}
            if args.module in ('audience','reach'):query_options['page']=args.page
            if metric_paged:query_options.update(page=args.page,all_pages=args.all_pages)
            if list_paged:query_options.update(page=args.page,all_pages=args.all_pages,audience_name=args.audience_name,reach_sys=args.reach_sys,reach_status=args.reach_status)
            if list_paged and args.all_pages:query_options['pagination_mode']='list_total_v1'
            if args.all_pages and section=='comprehensive-products-sku-full-pages':query_options['pagination_mode']='terminal_v1'
            if args.first_channel_id is not None:query_options['first_channel_id']=args.first_channel_id
            if args.second_channel_id is not None:query_options['second_channel_id']=args.second_channel_id
            if args.module=='benefits':query_options['rights_type']=args.rights_type
            if '--period' in explicit:query_options['period']=args.period
            if args.start_date is not None:query_options['start_day']=args.start_date
            if '--intimacy' in explicit:query_options['intimacy']=args.intimacy
            if args.second_id is not None:query_options['second_id']=args.second_id
            if '--behaviour' in explicit:query_options['behaviour']=args.behaviour
            for field in ('self_shop_id','compete1_shop_id','compete2_shop_id'):
                if getattr(args,field) is not None:query_options[field]=getattr(args,field)
        requests=0
        if args.evidence:
            evidence=Path(args.evidence).resolve();payload=read_evidence(evidence,'jd',args.store)
            if payload.get('date')!=args.date or payload.get('command')!=args.command:raise ValueError('证据日期或命令不符。')
            specs=payload['specs'];records=payload['records']
            query_options=payload.get('query_options')
            verify_specs(args.command,specs,args.date,query_options)
            for record,(report,params) in zip(records,specs,strict=True):verify_record(record,report,params,args.date,args.store)
        else:
            specs=[]
            if args.command=='user-analysis':
                from .user_analysis import specs as analysis_specs
                specs=analysis_specs(day=args.date,**query_options)
            elif args.command.startswith('category-'):
                report='category-summary' if args.command=='category-analysis' else 'category-trend'
                _,params=build(report,args.date,category_type=args.category_type,second_id=args.second_id,third_id=args.third_id);specs=[(report,params)]
            else:
                specs=[('user-dates',{})]
                if args.command=='user-overview':
                    specs.extend(('user-assets',build('user-assets',args.date,audience=k)[1]) for k in ('all','potential','new','old'))
                    specs.extend((k,build(k,args.date)[1]) for k in ('user-summary','user-diagnosis'))
                else:
                    k='user-'+args.section;specs.append((k,build(k,args.date,audience=args.audience,target=args.target)[1]))
            from .api_client import APIClient
            records=[]
            payload={'platform':'jd','store_key':args.store,'date':args.date,'command':args.command,'specs':specs,'records':records,'query_options':query_options}
            folder=output_folder(args.store,args.date);evidence=folder/'evidence.json'
            verify_specs(args.command,specs,args.date,query_options)
            try:
                minimum='0.9.20' if args.command=='user-analysis' and query_options['module'] in ('audience','reach','target-marketing') else '0.9.19' if args.command=='user-analysis' and query_options['module'] in ('pots','fans-summary','fans-feature','fans-quality','member-feature') else '0.9.18' if args.command=='user-analysis' else '0.9.17'
                if args.command=='user-analysis':
                    from .user_analysis import ADDITIONAL_READS,METRIC_CONTRACTS
                    if any(key in ADDITIONAL_READS or key in METRIC_CONTRACTS or 'firstChannelId' in p or p.get('fansType','999999')!='999999' or p.get('memberType','999999')!='999999' for key,p in specs):minimum='0.9.21'
                    if query_options['module']=='benefits':minimum='0.9.23'
                    if any(METRIC_CONTRACTS.get(key,{}).get('min_extension')=='0.9.24' for key,p in specs):minimum='0.9.24'
                    if any(ANALYSIS_CONTRACTS.get(key,{}).get('min_extension')=='0.9.25' for key,p in specs):minimum='0.9.25'
                    if any(ANALYSIS_CONTRACTS.get(key,{}).get('min_extension')=='0.9.26' for key,p in specs):minimum='0.9.26'
                    if any(ANALYSIS_CONTRACTS.get(key,{}).get('min_extension')=='0.9.27' for key,p in specs):minimum='0.9.27'
                with APIClient({'platform':'jd','store_key':args.store},min_extension=minimum) as client:
                    for report,params in specs:
                        raw,proof=client.request('shop-insights',args.date,scope={'report':report,'params':params});requests+=1
                        records.append({'response_text':client.last_response_text,'proof':proof});write_evidence(evidence,payload)
                        verify_record(records[-1],report,params,args.date,args.store)
                        if report=='analysis-insight-competitor-options' and any(ANALYSIS_CONTRACTS.get(k,{}).get('needs_competitor_auth') for k,p in specs):
                            from .user_options import check_competitors
                            check_competitors(normalize(json.loads(records[0]['response_text']),specs[0][0])['data'],normalize(raw,report)['data'],specs[-1][1])
                        if report=='analysis-member-overview-industry-auth' and len(specs)>1:
                            from .user_periods import check_industry_access
                            check_industry_access(normalize(raw,report)['data'])
                        if report=='analysis-member-overview-industry-categories' and len(specs)>1:
                            from .user_periods import check_industry_access
                            check_industry_access(normalize(json.loads(records[0]['response_text']),specs[0][0])['data'],normalize(raw,report)['data'],specs[-1][1])
                        if report=='analysis-fans-feature-intimacy-dates' and query_options.get('intimacy','all')!='all':
                            from .user_periods import check_intimacy_range
                            wanted=next(p for key,p in specs if key!='analysis-fans-feature-intimacy-dates')
                            payload['intimacy_range_verification']=check_intimacy_range(normalize(raw,report)['data'],wanted)
                        if query_options and query_options.get('all_pages'):
                            from .user_metrics import pagination_progress
                            pages=[{'section':key,'params':p,'result':normalize(json.loads(record['response_text']),key)} for record,(key,p) in zip(records,specs)]
                            progress=pagination_progress(pages,mode=query_options.get('pagination_mode'))
                            if not progress['complete']:
                                if len(specs)>=1000:raise ValueError('达到分页上限，未取全。')
                                specs.append((report,{**params,'pageNum':params['pageNum']+1}));write_evidence(evidence,payload)
                        if report=='user-dates':check_available(raw,args.date)
            except (ValueError,KeyError,TypeError,OSError,RuntimeError) as exc:
                payload['collection_error']=str(exc);write_evidence(evidence,payload)
                raise ValueError(str(exc)+'；已保存部分证据：'+str(evidence)) from exc
        results=[]
        if len(records)!=len(specs) or not specs:raise ValueError('证据数据段不完整。')
        for record,(key,params) in zip(records,specs,strict=True):
            raw=verify_record(record,key,params,args.date,args.store)
            if key=='user-dates':check_available(raw,args.date)
            results.append({'section':key,'params':params,'result':normalize(raw,key)})
        if query_options and query_options.get('pagination_mode')=='terminal_v1':
            from .user_metrics import terminal_page_result
            for item in results:item['result']=terminal_page_result(item['result'])
        report={'platform':'jd','store_key':args.store,'date':args.date,'command':args.command,'query_status':'partial' if any(item['result'].get('coverage',{}).get('official_business_code')=='2000' for item in results) else 'ok',
            'status':'partial','collection_mode':'replay' if args.evidence else 'live','source_requests_this_call':requests,
            'results':results,'evidence_path':str(evidence),'limitations':report_limitations(args.command,query_options)}
        if query_options and query_options.get('all_pages'):
            from .user_metrics import verify_pagination
            report['pagination_verification']=verify_pagination(results,mode=query_options.get('pagination_mode'))
        if query_options and query_options.get('intimacy','all')!='all':
            from .user_periods import check_intimacy_range
            if not results or results[0]['section']!='analysis-fans-feature-intimacy-dates':raise ValueError('缺少亲密度官方可查范围证据。')
            report['intimacy_range_verification']=check_intimacy_range(results[0]['result']['data'],results[1]['params'])
        if any(ANALYSIS_CONTRACTS.get(key,{}).get('needs_industry_auth') for key,p in specs):
            from .user_periods import check_industry_access
            report['industry_access_verification']=check_industry_access(results[0]['result']['data'],results[1]['result']['data'],specs[-1][1])
        if any(ANALYSIS_CONTRACTS.get(key,{}).get('needs_competitor_auth') for key,p in specs):
            from .user_options import check_competitors
            report['competitor_access_verification']=check_competitors(results[0]['result']['data'],results[1]['result']['data'],specs[-1][1])
        path=output_folder(args.store,args.date)/'report.json';save_json(path,report)
        print(json.dumps({**report,'report_path':str(path)},ensure_ascii=False));return 0
    except (ValueError,KeyError,TypeError,OSError,RuntimeError) as exc:
        print(str(exc),file=sys.stderr);return 1


def output_folder(store,day):
    return Path(__file__).resolve().parents[3]/'data/shop-insights'/store.replace(':','_')/day/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex[:8])
