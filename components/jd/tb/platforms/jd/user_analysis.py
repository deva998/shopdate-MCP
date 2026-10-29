"""Read contracts traced to official visitor, insight and legacy customer JS."""
from copy import deepcopy
from datetime import date,timedelta

GATEWAY='https://szgateway.jd.com'
JDSZ='https://jdsz.jd.com'
CHANNELS={'all':'99','app':'2','pc':'20','wx':'3','sq':'4','m':'1'}
FEATURES=('gender','ageSegment','provinceName','cityName','vipLevel','purchasePower','promotionSensitivity')
PAGES={
    'visitors':JDSZ+'/szweb/view/user/visitor-analysis-temp.html',
    'insight':JDSZ+'/szweb/view/customer/cus-insight-temp.html',
    'newold':JDSZ+'/szweb/view/customer/customer-ords-temp.html',
    'plus':JDSZ+'/szweb/view/user/plus-member-summary-temp.html',
    'pots':JDSZ+'/szweb/view/customer/customerpots-temp.html',
    'fans-summary':JDSZ+'/szweb/view/customer/fans-summary-temp.html',
    'fans-feature':JDSZ+'/szweb/view/customer/fans-feature-temp.html',
    'fans-quality':JDSZ+'/szweb/view/customer/fans-quality-temp.html',
    'member-feature':JDSZ+'/szweb/view/customer/member-feature-temp.html',
    'audience':JDSZ+'/szweb/view/customer/audience-list-temp.html',
    'reach':JDSZ+'/szweb/view/customer/audience-reach-temp.html',
    'target-marketing':JDSZ+'/szweb/view/venders/activity-indexs-temp.html'}
CONTRACTS={
    'analysis-visitor-time':{'origin':GATEWAY,'path':'/szajax/sz/flow/visitorAnalysis/getTimeDistributeTrendData.ajax','page':PAGES['visitors'],'schema':'visitor-time','response':'series'},
    'analysis-visitor-profile':{'origin':GATEWAY,'path':'/szpaas/szajax/shop/source/visitorAnalysis/getFeatureDistributeData.ajax','page':PAGES['visitors'],'schema':'visitor-profile','response':'data'},
    **{'analysis-insight-'+section:{'origin':GATEWAY,'path':'/szpaas/szajax/cust/insight/'+path+'.ajax','page':PAGES['insight'],
        'schema':'insight-trend' if section=='trend' else 'insight-compare','response':'data',
        'metric_note':'Uv为消费者PIN去重进店客户数，不等同浏览器UV。'} for section,path in {
            'summary':'getSummaryOverview','trend':'getSummaryTrend','detail':'getSummaryDetail'}.items()},
    **{'analysis-'+module+'-'+section:{'origin':JDSZ,'path':'/sz/api/'+prefix+'/'+path+'.ajax','page':PAGES[module],
        'schema':module+'-'+section,'response':'content'}
        for module,prefix in [('newold','cust/order'),('plus','plus/summary')]
        for section,path in [('summary','detail'),('trend','orderAnaly'),('profile','categoryDetail'),('brands','getTOP20dealBrand')]},
    'analysis-plus-special':{'origin':JDSZ,'path':'/sz/api/plus/summary/specialGoodsTable.ajax','page':PAGES['plus'],'schema':'plus-special','response':'content'},
    'analysis-plus-products':{'origin':JDSZ,'path':'/sz/api/plus/summary/goodsTable.ajax','page':PAGES['plus'],'schema':'plus-products','response':'content'},
}
CONTRACTS.update({
    'analysis-audience-detail':{'origin':GATEWAY,'path':'/szajax/sz/cust/audienceManage/audienceList.ajax','page':PAGES['audience'],'schema':'audience-base','response':'content'},
    'analysis-audience-special':{'origin':GATEWAY,'path':'/szajax/sz/cust/audienceManage/audienceList.ajax','page':PAGES['audience'],'schema':'audience-system','response':'content','metric_note':'系统推荐人群为当前列表，不按历史日期筛选；date仅为归档日期。'},
    'analysis-reach-detail':{'origin':GATEWAY,'path':'/szajax/sz/cust/audienceManage/reachList.ajax','page':PAGES['reach'],'schema':'reach','response':'content'},
    'analysis-target-marketing-summary':{'origin':JDSZ,'path':'/sz/api/vender/customer/getMarketAnalysis.ajax','page':PAGES['target-marketing'],'schema':'snapshot','response':'content','metric_note':'官方当前营销分析快照，统计区间以content.effect的startDate/endDate为准；不表示归档日期单日。'},
    **{'analysis-pots-'+section:{'origin':JDSZ,'path':'/sz/api/cust/potorder/'+path+'.ajax','page':PAGES['pots'],'schema':'date-only','response':'content'}
        for section,path in [('summary','detail'),('trend','orderAnaly')]},
    **{'analysis-fans-summary-'+section:{'origin':JDSZ,'path':'/sz/api/cust/fansSummary/'+path+'.ajax','page':PAGES['fans-summary'],'schema':'date-only','response':'content'}
        for section,path in [('summary','detail'),('trend','orderAnaly'),('detail','compare')]},
    **{'analysis-fans-feature-'+section:{'origin':JDSZ,'path':'/sz/api/cust/fansFeature/'+path+'.ajax','page':PAGES['fans-feature'],'schema':'fans-'+section,'response':'content'}
        for section,path in [('profile','categoryDetail'),('detail','channelAnalysis')]},
    'analysis-fans-quality-summary':{'origin':GATEWAY,'path':'/szpaas/szajax/customer/getFansQualityData.ajax','page':PAGES['fans-quality'],'schema':'snapshot','response':'data','metric_note':'当前关注用户质量快照，日期以官方updateTime为准，不代表请求历史日。'},
    **{'analysis-member-feature-'+section:{'origin':JDSZ if section!='detail' else GATEWAY,
        'path':('/sz/api/cust/memberFeature/' if section!='detail' else '/szpaas/szajax/cust/memberFeature/')+path+'.ajax',
        'page':PAGES['member-feature'],'schema':'member-'+section,'response':'content' if section!='detail' else 'data'}
        for section,path in [('profile','getMemberDetail'),('brands','getBrandGridList'),('detail','getChannelList')]}
})
ADDITIONAL_READS={
    'analysis-pots-profile':{'origin':JDSZ,'path':'/sz/api/cust/potorder/categoryDetail.ajax','page':PAGES['pots'],'schema':'date-only','response':'content'},
    'analysis-pots-brands':{'origin':JDSZ,'path':'/sz/api/cust/potorder/getTOP20dealBrand.ajax','page':PAGES['pots'],'schema':'pots-brands','response':'content'},
    'analysis-fans-summary-compare-trend':{'origin':JDSZ,'path':'/sz/api/cust/fansSummary/compareTrendData.ajax','page':PAGES['fans-summary'],'schema':'fans-compare-trend','response':'content'},
    'analysis-fans-feature-brands':{'origin':JDSZ,'path':'/sz/api/cust/fansFeature/getTOP20dealBrand.ajax','page':PAGES['fans-feature'],'schema':'fans-brands','response':'content'},
    'analysis-member-feature-trend':{'origin':GATEWAY,'path':'/szpaas/szajax/cust/memberFeature/getChannelTrend.ajax','page':PAGES['member-feature'],'schema':'member-channel-trend','response':'data','date_field':'DT'},
    'analysis-member-feature-channels-meta':{'origin':GATEWAY,'path':'/szpaas/szajax/cust/memberFeature/getChannelDescList.ajax','page':PAGES['member-feature'],'schema':'snapshot','response':'data','metric_note':'当前入会渠道字典，不表示历史日期统计。'},
}
CONTRACTS.update(ADDITIONAL_READS)
from .user_metrics import CONTRACTS as METRIC_CONTRACTS
CONTRACTS.update(METRIC_CONTRACTS)
PAGES['member-overview']='https://jdsz.jd.com/szweb/view/customer/member-overview-temp.html'
PAGES['benefits']='https://jdsz.jd.com/szweb/view/user/member-benefits-temp.html'
CONTRACTS['analysis-fans-feature-intimacy-dates']={'origin':JDSZ,'path':'/sz/api/cust/fansFeature/getTaskTime.ajax','page':PAGES['fans-feature'],'schema':'snapshot','response':'content','min_extension':'0.9.25','metric_note':'当前官方亲密度近三周可查窗口，date仅作归档。'}
CONTRACTS['analysis-member-overview-industry-auth']={'origin':GATEWAY,'path':'/szpaas/szajax/cust/memberOverview/checkIndustryAuth.ajax','page':PAGES['member-overview'],'schema':'snapshot','response':'data','min_extension':'0.9.25'}
CONTRACTS['analysis-member-overview-industry-categories']={'origin':GATEWAY,'path':'/szpaas/szajax/common/getUserCategoryList.ajax','page':PAGES['member-overview'],'schema':'member-industry-categories','response':'object-data','min_extension':'0.9.25'}
for _section,_path,_sort in [('order-users','getOrderRank','DealUserNum'),('order-orders','getOrderRank','DealOrderNum'),('order-amount','getOrderRank','DealAmt'),('recruit-members','getRecruitRank','AllMemberNum'),('recruit-new','getRecruitRank','NewMemberNum')]:
    _key='analysis-member-overview-rank-'+_section
    CONTRACTS[_key]={'origin':GATEWAY,'path':'/szpaas/szajax/cust/memberOverview/'+_path+'.ajax','page':PAGES['member-overview'],'schema':'member-industry-rank','response':'data','sort_field':_sort,'needs_industry_auth':True,'min_extension':'0.9.25'}
    for _period in ('week','month','custom'):CONTRACTS[_key+'-'+_period]={**deepcopy(CONTRACTS[_key]),'period':_period}
for _base in ('analysis-fans-feature-profile','analysis-fans-feature-brands','analysis-fans-feature-detail','analysis-member-feature-profile','analysis-member-feature-brands','analysis-member-feature-detail'):
    for _period in ('week','month','custom'):
        if _base.startswith('analysis-fans-') and _period=='custom':continue
        CONTRACTS[_base+'-'+_period]={**deepcopy(CONTRACTS[_base]),'schema':'period-get','native_schema':CONTRACTS[_base]['schema'],'base_report':_base,'period':_period,'min_extension':'0.9.25'}


from .user_options import extend_contracts
extend_contracts(CONTRACTS,PAGES)


def build_params(report,day,*,channel='all',feature='gender',compare='tb',segment=None,third_id=None,page=1,first_channel_id=None,second_channel_id=None,rights_type='2',start_day=None,intimacy='all',second_id=None,audience_name='',reach_sys=0,reach_status=0,behaviour='all',self_shop_id=None,compete1_shop_id=None,compete2_shop_id=None):
    from .shop_insights import historical_day
    if report not in CONTRACTS:raise ValueError('未登记用户分析接口。')
    schema=CONTRACTS[report]['schema']
    if schema not in ('snapshot','audience-system'):historical_day(day)
    if channel not in CHANNELS:raise ValueError('终端无效。')
    if type(page) is not int or not 1<=page<=1000:raise ValueError('页码必须为1至1000。')
    if schema=='audience-system' and page!=1:raise ValueError('系统推荐人群为固定当前列表，官方忽略翻页，不接受非第一页。')
    p={'date':day,'startDate':day,'endDate':day}
    if schema=='snapshot':return {}
    if schema=='fixed-meta':return {'menuCode':'custInsight','path':'/szweb/view/customer/cus-insight-temp.html'}
    if schema=='fans-channel-behaviour':
        if behaviour not in ('all','follow-day','other-day') or intimacy!='all':raise ValueError('渠道行为仅支持登记选项，不与亲密度混用。')
        p['indType']={'all':'999999','follow-day':'1','other-day':'2'}[behaviour];return p
    if schema=='list-filter':
        from .user_options import list_params
        return list_params(CONTRACTS[report]['native_schema'],day,start_day,page,audience_name,reach_sys,reach_status)
    if schema=='member-industry-categories':return {'categoryType':4,'showMainCode':True}
    if schema in ('member-industry-rank','oneservice-industry'):
        import re
        if any(not isinstance(value,str) or not re.fullmatch(r'\d+',value) for value in (second_id,third_id)):raise ValueError('行业会员查询须指定官方二级和三级类目ID。')
        c=CONTRACTS[report]
        if c.get('period'):
            from .user_periods import period_params
            p=period_params(day,c['period'],start_day)
        else:p['dateType']='day'
        p.update(secondIndId=second_id,thirdIndId=third_id)
        if c.get('sort_field'):p['sortField']=c['sort_field']
        return p
    if schema=='period-get':
        from .user_periods import period_params
        c=CONTRACTS[report];scope=period_params(day,c['period'],start_day)
        p=build_params(c['base_report'],day,channel=channel,feature=feature,compare=compare,segment=segment,third_id=third_id,page=page,first_channel_id=first_channel_id,second_channel_id=second_channel_id,rights_type=rights_type,behaviour=behaviour,intimacy=intimacy if c['native_schema']=='fans-channel-behaviour' else 'all',self_shop_id=self_shop_id,compete1_shop_id=compete1_shop_id,compete2_shop_id=compete2_shop_id)
        p.update({k:v for k,v in scope.items() if k!='dateType' or 'dateType' in p})
        if 'interval' in p:p['interval']=c['period'].upper() if c['period'] in ('week','month') else 'DAY'
        if c.get('native_date_type'):p['dateType']=c['native_date_type']
        if c['base_report'].startswith('analysis-fans-feature-') and c['native_schema']!='fans-channel-behaviour':
            if intimacy not in ('all','1','2','3','4') or intimacy!='all' and c['period']!='week':raise ValueError('亲密度分组仅允许完整自然周。')
            p['intimacy']='999999' if intimacy=='all' else intimacy
        return p
    if schema=='oneservice-range':
        from .user_periods import period_params
        p=period_params(day,CONTRACTS[report]['period'],start_day)
    if schema in ('audience-base','audience-system','reach'):
        p={'audienceName':'','startDate':day,'endDate':day,'pageNum':page,'pageSize':10}
        if schema=='audience-base':p['audienceType']=1
        elif schema=='audience-system':p.update(startDate='',endDate='',audienceStatus=0,audienceType=2)
        else:p.update(reachStatus=0,reachSys=0)
    elif schema in ('date-only','oneservice','oneservice-range'):
        if CONTRACTS[report].get('pagination'):p['pageNum']=page
        if CONTRACTS[report].get('window_days'):
            p['startDate']=(date.fromisoformat(day)-timedelta(days=CONTRACTS[report]['window_days']-1)).isoformat()
        if CONTRACTS[report].get('allowed_rights'):
            if rights_type not in CONTRACTS[report]['allowed_rights']:raise ValueError('权益类型无效。')
            p['rightsType']=rights_type
    elif schema=='fans-compare-trend':
        values={'all':'999999','fans':'1','nonfans':'2'}
        if (segment or 'all') not in values:raise ValueError('关注成交客户类型无效。')
        p['userType']=values[segment or 'all']
    elif schema in ('fans-profile','fans-detail','fans-brands'):
        p['intimacy']='999999'
        if schema!='fans-detail':
            values={'all':'999999','new':'1','deal':'2'}
            if (segment or 'all') not in values:raise ValueError('关注用户类型无效。')
            p['fansType']=values[segment or 'all']
        if schema=='fans-brands':
            import re
            if not isinstance(third_id,str) or not re.fullmatch(r'\d+',third_id):raise ValueError('品牌偏好必须指定官方三级类目ID。')
            p['ThirdIndId']=third_id
    elif schema.startswith('member-'):
        p['dateType']='day'
        if schema in ('member-profile','member-brands'):
            values={'all':'999999','card':'1','deal':'2'}
            if (segment or 'all') not in values:raise ValueError('品牌会员类型无效。')
            p['memberType']=values[segment or 'all']
        if schema in ('member-detail','member-channel-trend'):
            import re
            for field,value in [('firstChannelId',first_channel_id),('secondChannelId',second_channel_id)]:
                if value is not None:
                    if not isinstance(value,str) or not re.fullmatch(r'\d+',value):raise ValueError('入会渠道ID无效。')
                    p[field]=value
            if schema=='member-detail' and second_channel_id is not None:raise ValueError('渠道明细不接受secondChannelId。')
            if schema=='member-channel-trend' and first_channel_id is None:raise ValueError('入会渠道趋势必须指定官方首层渠道ID。')
        if schema=='member-brands':
            import re
            if not isinstance(third_id,str) or not re.fullmatch(r'\d+',third_id):raise ValueError('品牌偏好必须指定官方三级类目ID。')
            p['thirdIndId']=third_id
    elif schema=='visitor-time':p['indChannel']=CHANNELS[channel]
    elif schema=='visitor-profile':
        if feature not in FEATURES:raise ValueError('未登记的聚合画像字段。')
        p.update(dateType='day',interval='DAY',attributes=feature,groupType=feature)
        if channel!='all':p['platformCate1']=channel
        if feature in ('provinceName','cityName'):p.update(limit=10,sortField='jdr_sch_traffic_intr_brow_shop_cnt_shop_last_src',sortType='desc')
    elif schema.startswith('insight-'):
        p['dateType']='day'
        if schema in ('insight-compare','insight-competitors'):
            if compare not in ('hb','tb'):raise ValueError('比较类型必须为hb/tb。')
            p['compareType']=compare
        if schema=='insight-competitors':
            import re
            for field,value in [('selfShopId',self_shop_id),('compete1ShopId',compete1_shop_id),('compete2ShopId',compete2_shop_id)]:
                if value is None and field!='selfShopId':continue
                if not isinstance(value,str) or not re.fullmatch(r'\d+',value):raise ValueError('竞店查询须指定官方本店ID及可选竞店ID。')
                p[field]=value
    elif schema.endswith(('-summary','-trend')) or schema in ('plus-special','plus-products'):
        p['dimension']=1 if schema.startswith('plus-') else 0
        if schema=='plus-products':p.update(sortField='CustQty',sortType='desc')
    elif schema.endswith(('-profile','-brands')):
        values={'all':999999,'plus':2,'normal':3} if schema.startswith('plus-') else {'all':999999} if schema=='pots-brands' else {'all':999999,'new':0,'old':1}
        segment=segment or ('plus' if schema.startswith('plus-') else 'all')
        if segment not in values:raise ValueError('客户类型不适用于当前模块。')
        p['UserType' if schema.endswith('-brands') else 'userType']=values[segment]
        if schema.endswith('-brands'):
            import re
            if not isinstance(third_id,str) or not re.fullmatch(r'\d+',third_id):raise ValueError('品牌偏好必须指定官方三级类目ID。')
            p['ThirdIndId']=third_id
    return p


def validate_params(report,params):
    if not isinstance(params,dict) or report not in CONTRACTS:raise ValueError('未登记用户分析参数。')
    schema=CONTRACTS[report].get('native_schema',CONTRACTS[report]['schema'])
    if schema=='snapshot':
        if params:raise ValueError('当前质量快照不接受历史日期或额外参数。')
        return params
    if schema=='fixed-meta':
        if params!={'menuCode':'custInsight','path':'/szweb/view/customer/cus-insight-temp.html'}:raise ValueError('页面元数据参数不符。')
        return params
    if schema=='member-industry-categories':
        if params!={'categoryType':4,'showMainCode':True} or type(params.get('categoryType')) is not int or type(params.get('showMainCode')) is not bool:raise ValueError('行业类目字典参数无效。')
        return params
    reverse={v:k for k,v in CHANNELS.items()}
    channel=reverse.get(params.get('indChannel'),'all') if schema=='visitor-time' else params.get('platformCate1','all')
    population=params.get('UserType',params.get('userType'))
    segment={999999:'all',2:'plus',3:'normal',0:'new',1:'old'}.get(population)
    if schema in ('fans-profile','fans-brands'):segment={'999999':'all','1':'new','2':'deal'}.get(params.get('fansType'))
    if schema=='fans-compare-trend':segment={'999999':'all','1':'fans','2':'nonfans'}.get(params.get('userType'))
    if schema in ('member-profile','member-brands'):segment={'999999':'all','1':'card','2':'deal'}.get(params.get('memberType'))
    if any(type(value) is bool for value in params.values()):raise ValueError('参数类型无效。')
    expected=build_params(report,params.get('endDate'),channel=channel,feature=params.get('groupType','gender'),
        compare=params.get('compareType','tb'),segment=segment,third_id=params.get('ThirdIndId',params.get('thirdIndId')),page=params.get('pageNum',1),first_channel_id=params.get('firstChannelId'),second_channel_id=params.get('secondChannelId'),rights_type=params.get('rightsType','2'),start_day=params.get('startDate') if CONTRACTS[report].get('period')=='custom' or CONTRACTS[report]['schema']=='list-filter' else None,intimacy={'999999':'all','1':'1','2':'2','3':'3','4':'4'}.get(params.get('intimacy'),'all'),second_id=params.get('secondIndId'),audience_name=params.get('audienceName',''),reach_sys=params.get('reachSys',0),reach_status=params.get('reachStatus',0),behaviour={'999999':'all','1':'follow-day','2':'other-day'}.get(params.get('indType'),'all'),self_shop_id=params.get('selfShopId'),compete1_shop_id=params.get('compete1ShopId'),compete2_shop_id=params.get('compete2ShopId'))
    # Dict equality alone would accept booleans and numeric/string coercion.
    if params!=expected or any(type(params[k]) is not type(v) for k,v in expected.items()):raise ValueError('请求参数超出已核实用户分析范围。')
    return params


def specs(module,section,day,*,channel='all',feature=None,compare='tb',segment=None,third_id=None,page=1,first_channel_id=None,second_channel_id=None,rights_type='2',all_pages=False,period='day',start_day=None,intimacy='all',second_id=None,pagination_mode=None,audience_name='',reach_sys=0,reach_status=0,behaviour='all',self_shop_id=None,compete1_shop_id=None,compete2_shop_id=None):
    if pagination_mode is not None:
        valid=pagination_mode=='terminal_v1' and module=='benefits' and section=='comprehensive-products-sku-full-pages' or pagination_mode=='list_total_v1' and module in ('audience','reach') and section=='detail-filtered'
        if not valid or not all_pages or page!=1:raise ValueError('全量核验模式与登记数据表不符，必须从第一页读取。')
    if module not in PAGES:raise ValueError('该用户子模块尚未登记，不猜测接口。')
    sections={'visitors':('time','profile'),'insight':('summary','trend','detail'),'newold':('summary','trend','profile'),
        'plus':('summary','trend','profile','special','products'),'pots':('summary','trend'),
        'fans-summary':('summary','trend','detail'),'fans-feature':('profile','detail'),
        'fans-quality':('summary',),'member-feature':('profile','detail'),
        'audience':('detail','special'),'reach':('detail',),'target-marketing':('summary',),'member-overview':('summary','card','operable'),'benefits':('summary','special')}
    selected=list(sections[module]) if section=='overview' else [section]
    extras={'pots':('profile','brands'),'fans-summary':('compare-trend',),'fans-feature':('brands','intimacy-dates'),'member-feature':('brands','trend','channels-meta'),'newold':('brands',),'plus':('brands',)}
    extras.update(audience=('detail-filtered',),reach=('detail-filtered','options'),insight=('competitor-options','page-meta','competitors'))
    extras['member-feature']+=('options',)
    extras['fans-feature']+=('channel-behaviour',)
    for metric_module in ('member-overview','benefits'):
        prefix='analysis-'+metric_module+'-'
        extras[metric_module]=tuple(key.removeprefix(prefix) for key in CONTRACTS if key.startswith(prefix))
    if any(s not in sections[module]+extras.get(module,()) for s in selected):raise ValueError('数据段不适用于该用户子模块。')
    output=[]
    if module=='fans-feature' and period=='week' and intimacy!='all':output.append(('analysis-fans-feature-intimacy-dates',{}))
    for s in selected:
        key='analysis-'+('visitor' if module=='visitors' else module)+'-'+s
        if period!='day':key+='-'+period
        if CONTRACTS.get(key,{}).get('needs_competitor_auth'):output.extend([('analysis-insight-page-meta',build_params('analysis-insight-page-meta',day)),('analysis-insight-competitor-options',{})])
        if CONTRACTS.get(key,{}).get('needs_industry_auth') and not any(k=='analysis-member-overview-industry-auth' for k,p in output):output.extend([('analysis-member-overview-industry-auth',{}),('analysis-member-overview-industry-categories',{'categoryType':4,'showMainCode':True})])
        groups=([feature] if feature else list(FEATURES)) if module=='visitors' and s=='profile' else [None]
        for group in groups:
            output.append((key,build_params(key,day,channel=channel,feature=group or 'gender',compare=compare,segment=segment,third_id=third_id,page=1 if key=='analysis-audience-special' else page,first_channel_id=first_channel_id,second_channel_id=second_channel_id,rights_type=rights_type,start_day=start_day,intimacy=intimacy,second_id=second_id,audience_name=audience_name,reach_sys=reach_sys,reach_status=reach_status,behaviour=behaviour,self_shop_id=self_shop_id,compete1_shop_id=compete1_shop_id,compete2_shop_id=compete2_shop_id)))
    return deepcopy(output)
