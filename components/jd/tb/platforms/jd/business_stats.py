"""Fixed, read-only marketing and market contracts; no business write actions."""
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

ROOT = Path(__file__).resolve().parents[3]
JDSZ = 'https://jdsz.jd.com'
GATEWAY = 'https://szgateway.jd.com'
BASE = {'date':'$DAY','startDate':'$DAY','endDate':'$DAY'}
CONTRACTS = {}


def _add(key, path, page, template, *, origin=JDSZ, scope='historical_day_query', source, method='GET'):
    CONTRACTS[key] = {'method':method,'origin':origin,'path':path,'page':JDSZ+'/szweb/view/'+page,
                      'template':template,'scope':scope,'source':source,'min_extension':'0.9.28'}


for section, endpoint in [('summary','overview'),('trend','getMarketingTrend')]:
    _add('marketing-'+section,'/marketajax/biz/marketing/'+endpoint+'.ajax',
         'market/marketingtool-summary-temp.html',{**BASE,'skuOrSpu':1,'cmpType':0},
         origin=GATEWAY,source='marketing-summary.js: Xe / params / We')
for tab in ('single','suit','total','shop','product'):
    _add('tool-'+tab+'-summary','/sz/api/marketing/tools/'+tab+'/getSummaryData.ajax',
         'market/marketingtool-effect-temp.html',BASE,
         source='tool-effects.js: L / Mt / dateObj')
    _add('tool-'+tab+'-activities','/sz/api/marketing/tools/'+tab+'/getGridData.ajax',
         'market/marketingtool-effect-temp.html',{'tab':tab},scope='current_activity_list',
         source='tool-effects.js: L / Et / getAllData')
for section, endpoint in [('summary','getSummaryData'),('trend','getTrendData'),('types','getTypeGridData')]:
    _add('content-'+section,'/sz/api/contentSummary/'+endpoint+'.ajax',
         'market/content-summary-temp.html',{**BASE,'channel':'2'},
         source='content-summary.js: B / W / z / params / time helper O')
for section, endpoint in [('summary','getSummaryData'),('trend','getTrendData'),('products','getDetailData')]:
    template={**BASE,'dateType':'day','dateExtras':True}
    if section=='products':
        template.update(sortField='jdr_sch_deal_ord_amt_tenbillionsubsidy_sz',sortType='descend')
    _add('subsidy-'+section,'/szpaas/szajax/marketing/subsidyAnalysis/'+endpoint+'.ajax',
         'market/subsidy-analysis-temp.html',template,origin=GATEWAY,
         source='subsidy-service.js: mDt default GET / SzTime.getValue / handlers / frontend pagination')
_add('industry-buyers-options','/sz/api/industry/getSalesIndustryType.ajax',
     'industry/deal-cust-analysis-temp.html',{**BASE,'startCategoryLevel':1},
     source='industry-buyers.js: dataService.getCateData')
BUYER_BASE={**BASE,'indChannel':'99','firstIndId':'$FIRST_ID','secondIndId':'$SECOND_ID','thirdIndId':'$THIRD_ID'}
for section, endpoint in [('filters','getCrowdAttrList'),('profile','getCustAttrData'),
                          ('behaviour','getCustBehaviorData'),('consumption','getCustConsumptionData'),
                          ('preference','getCustBuyPreferenceData')]:
    template=BUYER_BASE if section=='filters' else {**BUYER_BASE,'range':'-1','gender':'-1','age':'-1','region':'-1','minPrice':'-1','maxPrice':'-1'}
    _add('industry-buyers-'+section,'/sz/api/customerAnalysis/'+endpoint+'.ajax',
         'industry/deal-cust-analysis-temp.html',template,
         source='industry-buyers.js: dataService.getCommonParams / crowdAttrType; legacy-util.js URL table')
    CONTRACTS['industry-buyers-'+section]['min_extension']='0.9.29'
for section,endpoint in [('summary','getSummary'),('trend','getSeries'),('activities','getActivitiesGrid')]:
    template={**BASE,'dateType':'day'}
    if section=='activities':template.update(sortField='ORDER_AMT',sortType='descend')
    _add('cross-sell-'+section,'/szpaas/szajax/market/upSell/'+endpoint+'.ajax',
         'market/match-buy-temp.html',template,origin=GATEWAY,
         source='cross-sell.js: De / onMetaChange / query / oe')
for section,endpoint in [('provinces','getVenderProvData'),('cities','getVenderCityData'),
                         ('categories','getVenderCateData'),('joined-trend','getVenderAddedTimeData')]:
    _add('industry-sellers-'+section,'/sz/api/customerAnalysis/'+endpoint+'.ajax',
         'industry/industry-shop-analysis-temp.html',{**BASE,'firstIndId':'$FIRST_ID','secondIndId':'$SECOND_ID','thirdIndId':'$THIRD_ID'},
         source='industry-sellers.js: curListParam / dataService; legacy-util.js URL table')
    CONTRACTS['industry-sellers-'+section]['min_extension']='0.9.29'
_add('compete-shop-options','/api/lowcode/common/getShopInfo.ajax',
     'compete/compete-shop.html',{},origin=GATEWAY,scope='current_metadata',
     source='compete-shop.js: compete-shop-selection fetcher')
for prefix,endpoint_prefix,page,source in [
    ('shop-gift','shopGift','shop-gift','shop-gift.js: Z'),
    ('coupon-share','fissionCoupon','coupon-share','coupon-share.js: ue')]:
    for section,endpoint in [('summary','overview'),('trend','trend')]:
        _add(prefix+'-'+section,'/marketajax/biz/'+endpoint_prefix+'/'+endpoint,
             'market/'+page+'-overview-temp.html',{'dateType':0,'startDate':'$DAY','endDate':'$DAY'},
             origin=GATEWAY,method='POST',source=source+' / onMetaChange / NaJA.b / getAllData')
        CONTRACTS[prefix+'-'+section]['min_extension']='0.9.29'
_add('coupon-share-activities','/marketajax/biz/fissionCoupon/activity',
     'market/coupon-share-overview-temp.html',{},origin=GATEWAY,scope='current_activity_list',
     source='coupon-share.js: ue.getActivity / NaJA.a / getAllData')
CONTRACTS['coupon-share-activities']['min_extension']='0.9.29'
_add('shop-gift-activities','/marketajax/biz/shopGift/activity',
     'market/shop-gift-overview-temp.html',{},origin=GATEWAY,scope='current_activity_list',
     source='shop-gift.js: Z.getActivity / NaJA.a / getAllData')
CONTRACTS['shop-gift-activities']['min_extension']='0.9.29'
for section,endpoint in [('summary','overview'),('trend','lineChart')]:
    _add('gift-money-'+section,'/marketajax/biz/gift/money/'+endpoint,
         'market/gift-money-promotion-temp.html',{**BASE,'dateType':'day','tab':1012},
         origin=GATEWAY,method='POST',source='gift-money.js: me / NaJA.b / dateParams / getAllData, default tab1012')
    CONTRACTS['gift-money-'+section]['min_extension']='0.9.29'
_add('gift-money-activities','/marketajax/biz/data/query/getDataPage',
     'market/gift-money-promotion-temp.html',{'activityId':'','pageNumber':1,'pageSize':10,'tab':1012,
        'serviceId':'eco_data_storage','selectId':'eco_data_storage_279#eco_data_storage_280'},
     origin=GATEWAY,method='POST',scope='current_activity_first_page',source='gift-money.js: oe.getGrid / getAllData / serviceId / selectId')
CONTRACTS['gift-money-activities']['min_extension']='0.9.34'
CONTRACTS['gift-money-activities']['template']['pageNumber']='$PAGE'
for section,endpoint,select_id in [('summary','overview','consume_329'),('trend','lineChart','consume_330')]:
    _add('expansion-money-'+section,'/pzjmarketajax/biz/data/query/'+endpoint,
         'market/expansion-money-overview-temp.html',{'startDate':'$DAY','endDate':'$DAY','dateType':'day',
            'serviceId':'consume','selectId':select_id,'activityType':'1'},origin=GATEWAY,method='POST',
         source='expansion-money.js: allowance gateway / ol / mt / onMetaChange / getAllData default activityType1')
    CONTRACTS['expansion-money-'+section]['min_extension']='0.9.29'

from .business_metrics import CONTRACTS as METRIC_CONTRACTS
CONTRACTS.update(METRIC_CONTRACTS)
for section,endpoint in [('summary','getCoreIndicatorsInfo'),('shops','getCompetitionShopDetail'),
                         ('products','getCompetitionShopProductList'),('sources','getViewSourceData'),('keywords','getViewKeyWordData')]:
    template={**BASE,'indChannel':'2' if section=='sources' else '99'}
    if section=='products':template['type']='1'
    _add('compete-overview-'+section,'/sz/api/competitionAnalysis/'+endpoint+'.ajax',
         'compete/compete-shop-overview-temp.html',template,
         source='compete-overview-legacy.js: g / v / k / O / P, configured shops; legacy-util.js: competitionAnalysis.shopOverview / channelList')
    CONTRACTS['compete-overview-'+section]['min_extension']='0.9.30'
for section,endpoint in [('summary','getLossSummaryData'),('trend','getLossSummaryTrendData'),
                         ('shops','getLossShopDestinationData'),('products','getLossProductDestinationData')]:
    template={**BASE,'indChannel':'99'}
    if section=='products':template['type']=0
    _add('compete-loss-'+section,'/sz/api/competitionAnalysis/'+endpoint+'.ajax',
         'compete/compete-loss-temp.html',template,
         source='compete-loss-legacy.js: C / P / y / I / native proDestGridType0; legacy-util.js: competitionAnalysis.lossAnalysis')
    CONTRACTS['compete-loss-'+section]['min_extension']='0.9.30'
for type_name,type_code in [('article','1'),('video','2'),('live','3')]:
    for section,endpoint in [('summary','getSummaryData'),('trend','getTrendData'),
                             ('contents','getGridDataLive' if type_code=='3' else 'getGridData'),
                             ('sources','getGridDataNew'),('products','getGridDataNew')]:
        template={**BASE,'dateType':'day','channel':'2','contenType':type_code,'subContentType':'999999'}
        if section in ('sources','products'):template.update(type='source' if section=='sources' else 'product',orderBy='LedSkuDetUV',pageOrder='desc',skuId='')
        key='content-detail-'+type_name+'-'+section
        _add(key,'/sz/api/typeAnalyse/'+endpoint+'.ajax','market/type-analyse-temp.html',template,
             source='content-detail.js: f / h / getAllData / changeDate / native params / xe / we / je / Se')
        CONTRACTS[key]['min_extension']='0.9.31'
_add('content-detail-subtypes','/sz/api/typeAnalyse/getSubContentType.ajax','market/type-analyse-temp.html',
     {**BASE,'dateType':'day','channel':'2','contenType':'1'},source='content-detail.js: changeDate / changeChannel, subContentType deleted')
CONTRACTS['content-detail-subtypes']['min_extension']='0.9.31'
for section,endpoint in [('summary','getCoreIndicatorsInfoRtime'),('trend','getCoreIndicatorsTrendRtime'),
                         ('shops','getCompetitionShopDetailRtime'),('products','getCompetitionShopProductListRtime'),
                         ('sources','getViewSourceDataRtime')]:
    template={'indChannel':'2' if section=='sources' else '99'}
    if section=='products':template['type']='1'
    if section=='trend':template['indId']='UV'
    _add('compete-realtime-'+section,'/sz/api/competitionAnalysis/'+endpoint+'.ajax',
         'compete/compete-shop-monitor-temp.html',template,scope='current_realtime',
         source='compete-realtime-legacy.js: f / I default UV / v / b / A; legacy-util.js shopOverviewRtime')
    CONTRACTS['compete-realtime-'+section]['min_extension']='0.9.32'
for key,endpoint in [('compete-loss-product-list','getLossProList'),('compete-search-list','getSearchCmptProList')]:
    _add(key,'/sz/api/competitionAnalysis/'+endpoint+'.ajax',
         'compete/compete-loss-temp.html',{**BASE,'indChannel':'99','unitType':0},
         source='compete-loss-legacy.js: proLossCtrl/searchLossCtrl i/o curParam, default SPU unit0, getLossList x; legacy-util.js lossAnalysis')
    CONTRACTS[key]['min_extension']='0.9.32'
for key,path in [('compete-shop-filters','/api/common/getDims.ajax?menuCode=competeShop'),
                 ('compete-shop-dates','/api/lowcode/common/commonParam.ajax?menuCode=competeShop')]:
    _add(key,path,'compete/compete-shop.html',{},origin=GATEWAY,scope='current_metadata',
         source='competeShop native resource inventory; modern shared global-page and date-picker metadata requests')
    CONTRACTS[key]['min_extension']='0.9.32'


COMPARE_METRICS=['jdr_sch_trade_deal_ord_ord_amt_sz_trade_deal_snapshot',
    'jdr_sch_traffic_enter_shop__browse_page_cnt_shop_last_src',
    'fo_jdr_sch_industry_deal_rate',
    'jdr_sch_sku_add_cart_sku_user_qtty_product_user_cart_add_minus_sz_bsg_shoppingcart@increase']
for section in ('summary','trend'):
    template={'realtime':False,'interval':'DAY','dateType':'day','startDate':'$DAY','endDate':'$DAY',
        'compareStartDate':'$PREV','compareEndDate':'$PREV','compareType':'hb',
        'monitorDim':'all','channel':'all','selfShopId':['$SELF_SHOP'],'compareShopId1':['$COMPARE_SHOP'],
        'groups':['shop'] if section=='summary' else ['dt','shop'],
        'attributes':['shop'] if section=='summary' else ['dt','shop'],
        'indicators':COMPARE_METRICS if section=='summary' else COMPARE_METRICS[:1]}
    if section=='trend':template['trendType']='segment'
    _add('compete-compare-'+section,'/api/lowcode/competeShop/summary/'+section+'.ajax',
        'compete/compete-shop.html',template,origin=GATEWAY,method='POST',
        source='compete-shop.js: U/Pt/kt/Me, whole-shop, single day hb; modern-datepicker module42842 SzDPParams/Jt/Rt; module13989 n7 POST')
    CONTRACTS['compete-compare-'+section]['min_extension']='0.9.33'
    if section=='trend':
        template.update(startDate='$START',compareStartDate='$COMPARE_START')
        CONTRACTS['compete-compare-trend']['window_days']=7
        CONTRACTS['compete-compare-trend']['source']+='; modern-chunks/8980 module76802 h(e,6) seven-day trendParams'

for unit in ('sku','spu'):
    for mode,metric in [('trade',COMPARE_METRICS[0]),('flow','jdr_sch_traffic_brow_sku__page_cnt_traffic_plat_item_di_sz_bsg')]:
        template=deepcopy(CONTRACTS['compete-compare-summary']['template'])
        for k in ('groups','attributes','indicators'):template.pop(k)
        template.update(proType=unit,groups=[unit+'_id'],indicators=[metric],sortField=metric,sortOrder='desc')
        key='compete-compare-'+unit+'-'+mode
        _add(key,'/api/lowcode/competeShop/product/top.ajax','compete/compete-shop.html',template,
            origin=GATEWAY,method='POST',source='compete-shop.js: cr/sr, native SKU/SPU and trade/flow tabs; Bt/qt metrics')
        CONTRACTS[key]['min_extension']='0.9.33'
FLOW_UV='jdr_sch_traffic_brow_sku_cnt_jd_unified_attribution_sz'
template=deepcopy(CONTRACTS['compete-compare-summary']['template'])
template.pop('attributes')
template.update(channel='app',groups=['jdr_sch_traffic_cha_last_field_src_rmad_sz_1','shop'],
    indicators=[FLOW_UV,FLOW_UV+'/jdr_sch_traffic_brow_sku__page_cnt_traffic_plat_item_di_sz_bsg##customProportion',
        'jdr_sch_traffic_intr_ord_ord_amt_jd_unified_attribution_trade_deal_snapshot_sz',
        'fo_jdr_sch_fo_jdr_sch_traffic_intr_ord_cvr_deal_sz',
        'jdr_sch_traffic_intr_ord_ord_cnt_jd_unified_attribution_trade_deal_snapshot_sz'],
    sortField=FLOW_UV,sortType='desc',limit=1000)
_add('compete-compare-sources','/api/lowcode/competeShop/flow/table.ajax','compete/compete-shop.html',template,
    origin=GATEWAY,method='POST',source='compete-shop.js: Rr/Kr, gr/vr/jr/yr/Or and wr, APP first source level fixed limit1000')
CONTRACTS['compete-compare-sources']['min_extension']='0.9.33'

for unit in ('spu','sku'):
    key='compete-product-'+unit+'-options'
    _add(key,'/api/lowcode/common/getProductInfo.ajax','industry/compete-product.html',
        {'proType':unit,'realtime':False},origin=GATEWAY,scope='current_metadata',
        source='compete-product.js: D fetchAllCompeteProduct GET Fe; D({proType:i,realtime:d}); official self/compare monitored dictionary')
    CONTRACTS[key].update(min_extension='0.9.35',product_unit=unit)
    for section in ('summary','trend'):
        template={'realtime':False,'interval':'DAY','dateType':'day','startDate':'$DAY','endDate':'$DAY',
            'compareStartDate':'$PREV','compareEndDate':'$PREV','compareType':'hb','channel':'all','proType':unit,
            'self'+unit.title()+'Id':['$SELF_PRODUCT'],'compare'+unit.title()+'Id1':['$COMPARE_PRODUCT'],
            'groups':[unit+'_id'],'attributes':[unit+'_id'],
            'indicators':COMPARE_METRICS[:1] if section=='trend' else [COMPARE_METRICS[0],
                'jdr_sch_traffic_brow_sku__page_cnt_traffic_plat_item_di_sz_bsg']}
        if section=='trend':template.update(startDate='$START',compareStartDate='$COMPARE_START',groups=[unit+'_id','dt'],attributes=[unit+'_id','dt'],trendType='segment')
        key='compete-product-'+unit+'-'+section
        _add(key,'/api/lowcode/competeProduct/summary/'+section+'.ajax','industry/compete-product.html',template,
            origin=GATEWAY,method='POST',source='compete-product.js: native $ product ids, core M/nt/at; combo trendDayRange29 ->30 days; selected official monitored dictionary only')
        CONTRACTS[key].update(min_extension='0.9.35',product_unit=unit,requires_products=True)
        if section=='trend':CONTRACTS[key]['window_days']=30

PRODUCT_CORE_ALL=[COMPARE_METRICS[0],'jdr_sch_trade_deal_ord_sku_qtty_sz_trade_deal_snapshot',
    'jdr_sch_trade_deal_ord_ord_qtty_sz_trade_deal_snapshot','jdr_sch_traffic_brow_sku__page_qtty_traffic_plat_item_di_sz_bsg',
    'jdr_sch_traffic_brow_sku__page_cnt_traffic_plat_item_di_sz_bsg','jdr_sch_search_exposure_sku_piece_search_standard_sz',
    'jdr_sch_search_click_page_qtty_search_standard_sz','jdr_sch_search_click_user_cnt_search_standard_sz',
    'fo_jdr_sch_click_page_qtty_exposure_sku_piece_rate_search_standard_sz',COMPARE_METRICS[3],COMPARE_METRICS[2],
    'fo_jdr_sch_trade_deal_ord_amt_user_sz_trade_deal_snapshot']
PRODUCT_FLOW_METRICS=CONTRACTS['compete-compare-sources']['template']['indicators']
for unit in ('sku','spu'):
    base=CONTRACTS['compete-product-'+unit+'-summary']['template']
    for section,path in [('core-all','summary/summary'),('sources','flow/table'),
            ('keywords-flow','keyword/top'),('keywords-deal','keyword/top'),('customers','detail/crowdComposition')]:
        template=deepcopy(base);extra={}
        if section=='core-all':template['indicators']=PRODUCT_CORE_ALL
        elif section=='sources':
            template.update(channel='app',groups=[unit+'_id','jdr_sch_traffic_cha_last_field_src_rmad_sz_1'],
                attributes=[unit+'_id','jdr_sch_traffic_cha_last_field_src_rmad_sz_1'],
                indicators=PRODUCT_FLOW_METRICS,sortField=FLOW_UV,sortType='desc')
            extra['schema']='product_aux'
        elif section.startswith('keywords-'):
            template.update(channel='app',groups=['jdr_sch_traffic_cha_detail_value_name',unit+'_id'],
                attributes=['jdr_sch_traffic_cha_detail_value_name',unit+'_id'],
                indicators=[PRODUCT_FLOW_METRICS[0],PRODUCT_FLOW_METRICS[2]],
                sortField=PRODUCT_FLOW_METRICS[0] if section=='keywords-flow' else PRODUCT_FLOW_METRICS[2],sortType='desc',limit=200)
            extra['schema']='product_aux'
        else:
            template.pop('indicators')
            template.update(groups=['gender','age_segment','dim_province_name','dim_city_name'],
                attributes=['gender','age_segment','dim_province_name','dim_city_name'],
                indicator='jdr_sch_user_deal_ord_user_cnt_sz_user_deal_snapshot',
                sortField='jdr_sch_user_deal_ord_user_cnt_sz_user_deal_snapshot',sortType='desc')
            extra['schema']='product_aux'
        key='compete-product-'+unit+'-'+section
        _add(key,'/api/lowcode/competeProduct/'+path+'.ajax','industry/compete-product.html',template,
            origin=GATEWAY,method='POST',source='compete-product.js: ye/ge/_e native indicators; core M/nt, flow mt, keyword jt flow/deal tabs limit200, customer Qt singular indicator; official monitored dictionary')
        CONTRACTS[key].update(min_extension='0.9.36',product_unit=unit,requires_products=True,**extra)
for key,path in [('compete-monitor-product-count','/api/lowcode/competeMonitor/detail/getCount.ajax'),
                 ('compete-monitor-shop-count','/api/lowcode/competeMonitor/detail/getShopCount.ajax'),
                 ('compete-monitor-filters','/api/common/getDims.ajax?menuCode=competeMonitor')]:
    _add(key,path,'compete/compete-monitor.html',{},origin=GATEWAY,scope='current_metadata',
        source='compete-monitor.js: Et getCompeteCollection Fe GET / Ro getShopCount Fe GET / global page menuCode competeMonitor dims')
    CONTRACTS[key]['min_extension']='0.9.36'

MONITOR_BASE={'realtime':False,'interval':'DAY','dateType':'day','startDate':'$DAY','endDate':'$DAY',
    'compareStartDate':'$PREV','compareEndDate':'$PREV','compareType':'hb','channel':'all','monitorDim':'all'}
MONITOR_PRODUCT_METRICS=[PRODUCT_CORE_ALL[i] for i in (0,1,2,4,6,9)]+[
    'jdr_sch_trade_cross_purchase_sku_qtty_sz_trade_deal_snapshot','jdr_sch_user_cross_purchase_user_cnt_sz_user_deal_snapshot']
MONITOR_SHOP_METRICS=[COMPARE_METRICS[0],COMPARE_METRICS[1],'jdr_sch_traffic_enter_shop__browse_page_qtty_shop_last_src',
    PRODUCT_CORE_ALL[1],PRODUCT_CORE_ALL[2],PRODUCT_CORE_ALL[11],COMPARE_METRICS[2],COMPARE_METRICS[3],
    PRODUCT_CORE_ALL[6],PRODUCT_CORE_ALL[7],'jdr_sch_traffic_brow_traffic_qtty_traffic_plat_item_di_sz_bsg@jdr_gt_visits',
    'jdr_sch_traffic_brow_traffic_qtty_traffic_plat_item_di_sz_bsg@jdr_gt_qtty']


def _monitor(key,path,template,**metadata):
    _add(key,'/api/lowcode/competeMonitor/'+path+'.ajax','compete/compete-monitor.html',template,
        origin=GATEWAY,method='POST',source='compete-monitor.js: T/Ut/Be product table; Mt/Me trend; Wt lossTarget; mo/No/So/ko shops; qo shop trend; Ho shop productTop; explicit all view omits categories')
    CONTRACTS[key].update(min_extension='0.9.37',schema='monitor_pending',**metadata)


for unit in ('sku','spu'):
    _monitor('compete-monitor-'+unit+'-products','detail/table',
        {**MONITOR_BASE,'proType':unit,'groups':[unit+'_id'],'attributes':[unit+'_id'],
         'indicators':[code for m in MONITOR_PRODUCT_METRICS[:6] for code in (m,m+'##compare')]+MONITOR_PRODUCT_METRICS[6:],
         'sortField':COMPARE_METRICS[0],'sortType':'desc'},product_unit=unit)
    _monitor('compete-monitor-'+unit+'-trend','detail/trend',
        {**MONITOR_BASE,'startDate':'$START','compareStartDate':'$COMPARE_START','groups':['dt'],'attributes':['dt'],
         'trendType':'segment','indicators':MONITOR_PRODUCT_METRICS,unit+'_id':'$TARGET'},
        product_unit=unit,target_kind='product',target_field=unit+'_id',window_days=7)
    _monitor('compete-monitor-'+unit+'-loss','detail/tableLoss',
        {**MONITOR_BASE,'proType':unit,'indicators':MONITOR_PRODUCT_METRICS[6:],'sortField':MONITOR_PRODUCT_METRICS[-1],
         'sortType':'desc','lossTarget'+unit.title():['$TARGET']},
        product_unit=unit,target_kind='product',target_field='lossTarget'+unit.title(),target_array=True)
    top={k:v for k,v in MONITOR_BASE.items() if k not in ('realtime','compareType','compareStartDate','compareEndDate')}
    top.update(shopId='$TARGET',proType=unit,indicators=[COMPARE_METRICS[0],PRODUCT_CORE_ALL[4]])
    _monitor('compete-monitor-shop-'+unit+'-top','shop/productTop',top,product_unit=unit,target_kind='shop',target_field='shopId')
_monitor('compete-monitor-shops','shop/table',
    {**{k:v for k,v in MONITOR_BASE.items() if k!='realtime'},'indicators':[code for m in MONITOR_SHOP_METRICS for code in (m,m+'##compare')],
     'sortField':COMPARE_METRICS[0],'sortOrder':'desc'})
_monitor('compete-monitor-shop-trend','shop/trend',
    {**{k:v for k,v in MONITOR_BASE.items() if k not in ('realtime','compareStartDate','compareEndDate')},
     'startDate':'$START','shopId':'$TARGET','trendType':'segment','indicators':COMPARE_METRICS[:1]},
    target_kind='shop',target_field='shopId',window_days=7)


# Native APP drilldowns: station (2), then homepage (2007), never arbitrary source IDs.
for prefix in ('compete-compare','compete-product-sku','compete-product-spu'):
    for level in (2,3):
        key=prefix+'-sources-level'+str(level)
        c=deepcopy(CONTRACTS[prefix+'-sources'])
        c.update(min_extension='0.9.38',source_level=level)
        c['source']+='; compete-shop.js Tr/Vr or compete-product.js tree handler: flowSrcId arrays, next-level groups/attributes; native homepage 2/2007'
        t=c['template'];field='jdr_sch_traffic_cha_last_field_src_rmad_sz_'+str(level)
        t['groups']=[field,'shop'] if prefix=='compete-compare' else [c['product_unit']+'_id',field]
        if 'attributes' in t:t['attributes']=list(t['groups'])
        t['flowSrcId1']=['2']
        if level==3:t['flowSrcId2']=['2007']
        if prefix!='compete-compare':t.update(pageIndex=1,pageSize=100)
        CONTRACTS[key]=c
for key,c in CONTRACTS.items():
    if key.startswith(('compete-product-','compete-compare-','compete-monitor-')) and c['template'].get('channel')=='all':
        c['template']['channel']='$CHANNEL';c['channel_options']=['all','app'];c['min_extension']='0.9.38'
for tab in ('single','total'):
    key='tool-'+tab+'-filter-options'
    _add(key,'/sz/api/marketing/tools/'+tab+'/getTypeData.ajax','market/marketingtool-effect-temp.html',{},
        scope='current_metadata',source='tool-effects.js: Pt fetch getSingleTypeData/getTypeData without params; type/people/platform dictionaries')
    CONTRACTS[key]['min_extension']='0.9.38'


GIFT_DETAIL_METRICS=['dealPins','directAmount','indirectAmount','indirectSaleQtty','indirectSkus','promtPrefrAmt','promtPrefrAmtPer','visitDealRate','visitPins','visitRate']
for section,endpoint,select in [('info','getActivityBaseInfo','consume_282'),('overview','getActivityOverview','consume_282'),
        ('daily','getActivityTrend','consume_292'),('trend','getActivityLineChart','consume_284'),
        ('products','getSkuDataPage','eco_data_storage_290#eco_data_storage_291')]:
    key='gift-money-detail-'+section
    template={'activityId':'$TARGET','tab':1012,'serviceId':'consume','selectId':select}
    if section in ('overview','daily'):template['filterPropertys']=GIFT_DETAIL_METRICS
    if section in ('daily','trend'):template.update(BASE,dateType='day')
    if section=='products':template.update(serviceId='eco_data_storage',pageNumber=1,pageSize=10,skuId='')
    _add(key,'/marketajax/biz/data/query/'+endpoint,'market/gift-money-detail-temp.html',template,origin=GATEWAY,method='POST',
        scope='current_activity_metadata' if section=='info' else 'activity_lifetime' if section=='overview' else 'current_activity_product_first_page' if section=='products' else 'historical_day_query',
        source='gift-money-detail.js: native getInfoData/getOverview/getDayData/getGridData, tab1012, SERVICEID/SELECTID; PiNH business gateway, NaJA.b POST')
    CONTRACTS[key].update(min_extension='0.9.38',target_kind='activity',target_field='activityId',schema='gift_detail_pending')


# Native modern category view uses only saleOrdCate3 when fullCascaderLevel is false.
for key,c in CONTRACTS.items():
    if key.startswith(('compete-compare-','compete-monitor-')) and c['template'].get('monitorDim')=='all':
        c['competition_category_options']='compete-shop-filters' if key.startswith('compete-compare-') else 'compete-monitor-filters'
        c['min_extension']='0.9.39'
for key,path in [('compete-config-products','competitionProduct/competeProList'),('compete-config-shops','competitionShop/competeShoplist')]:
    _add(key,'/api/lowcode/competeConfig/'+path+'.ajax','compete/compete-config.html',{},origin=GATEWAY,method='POST',scope='current_configuration_readonly',
        source='compete-config.js: f/g native list POST via n7({params:L()}), L returns {}; excludes every add/del route')
    CONTRACTS[key].update(min_extension='0.9.39',schema='configuration_read_pending')


_add('compete-realtime-config-shops','/sz/api/competitionAnalysis/getAllCompetitionShopData.ajax',
    'compete/compete-shop-config-temp.html',{},scope='current_configuration_readonly',
    source='official legacy-util.js competitionAnalysis.competitionConfig.getAllCompetitionShopData; registered GET list-only probe, live identity/count/time/follower fields must match native realtime config page')
CONTRACTS['compete-realtime-config-shops'].update(min_extension='0.9.40',schema='realtime_config_pending')


def params(report, day, *, category=None,shops=None,products=None,target=None,page=1,channel=None,competition_category=None,archive=False):
    if report not in CONTRACTS:
        raise ValueError('未登记的只读统计报告。')
    parsed=date.fromisoformat(day)
    today=datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    realtime=CONTRACTS[report]['scope']=='current_realtime'
    if parsed.isoformat()!=day or (day>today if realtime and archive else day!=today if realtime else day>=today):
        if realtime:raise ValueError('实时竞争统计只读取北京时间今日快照；历史日期仅支持已保存证据重放。')
        raise ValueError('归档日期须为北京时间完整历史日。')
    if channel is not None and (not isinstance(channel,str) or channel not in CONTRACTS[report].get('channel_options',[])):
        raise ValueError('该报告仅接受登记的渠道all/app；来源查询固定APP，其他报告不接受渠道筛选。')
    if report in METRIC_CONTRACTS:
        from .business_metrics import params as metric_params
        return metric_params(report,day,archive=archive)
    c=CONTRACTS[report]
    tokens={'$DAY':day,'$START':(parsed-timedelta(days=c.get('window_days',1)-1)).isoformat(),
        '$COMPARE_START':(parsed-timedelta(days=c.get('window_days',1))).isoformat(),'$PREV':(parsed-timedelta(days=1)).isoformat()}
    tokens['$CHANNEL']=channel or 'all'
    output=deepcopy(c['template'])
    for key,value in output.items():
        if isinstance(value,str):
            for token,replacement in tokens.items():value=value.replace(token,replacement)
            output[key]=value
    if c.get('target_field'):
        if not isinstance(target,str) or not re.fullmatch(r'[1-9]\d*',target):raise ValueError('下钻对象须为官方监控字典或活动列表内的数字ID。')
        output[c['target_field']]=[target] if c.get('target_array') else target
    elif target is not None:raise ValueError('该报告不接受下钻对象。')
    if CONTRACTS[report].get('requires_products'):
        unit=CONTRACTS[report]['product_unit'].title()
        fields={'self'+unit+'Id','compare'+unit+'Id1'}
        if not isinstance(products,dict) or set(products)!=fields or any(not isinstance(v,list) or len(v)!=1 or not isinstance(v[0],str) or not re.fullmatch(r'[1-9]\d*',v[0]) for v in products.values()) or len({v[0] for v in products.values()})!=2:raise ValueError('竞品对比须绑定官方字典的本品及一个已监控竞品。')
        output.update(deepcopy(products),compareStartDate=(parsed-timedelta(days=CONTRACTS[report].get('window_days',1))).isoformat(),compareEndDate=(parsed-timedelta(days=1)).isoformat())
        if report.endswith('-trend'):output['startDate']=(parsed-timedelta(days=29)).isoformat()
    if report=='gift-money-activities':
        if type(page) is not int or not 1<=page<=2000:raise ValueError('礼金分页须为1至2000的整数。')
        output['pageNumber']=page
    elif page!=1:raise ValueError('该报告不支持分页参数。')
    if report.startswith('compete-compare-'):
        if not isinstance(shops,dict) or set(shops)!= {'selfShopId','compareShopId1'} or any(not isinstance(v,list) or len(v)!=1 or not isinstance(v[0],str) or not re.fullmatch(r'[1-9]\d*',v[0]) for v in shops.values()) or shops['selfShopId']==shops['compareShopId1']:raise ValueError('竞店对比须绑定本店和一个已配置竞店。')
        output.update(deepcopy(shops))
        output.update(compareStartDate=(parsed-timedelta(days=1)).isoformat(),compareEndDate=(parsed-timedelta(days=1)).isoformat())
        if report=='compete-compare-trend':
            output.update(startDate=(parsed-timedelta(days=6)).isoformat(),compareStartDate=(parsed-timedelta(days=7)).isoformat())
    for key,token in [('firstIndId','$FIRST_ID'),('secondIndId','$SECOND_ID'),('thirdIndId','$THIRD_ID')]:
        if output.get(key)==token:
            value=(category or {}).get(key)
            if type(value) is not int or value<=0 or key!='thirdIndId' and value==999999:
                raise ValueError('行业统计须绑定官方有效二三级类目，不支持全部二级占位值。')
            output[key]=value
    if competition_category is not None:
        ids=competition_category.get('saleOrdCate3') if isinstance(competition_category,dict) else None
        if not c.get('competition_category_options') or set(competition_category)!={'saleOrdCate3'} or not isinstance(ids,list) or not 1<=len(ids)<=1000 or any(not isinstance(v,str) or not re.fullmatch(r'[1-9]\d*',v) for v in ids) or len(set(ids))!=len(ids):raise ValueError('类目视角须绑定官方有效三级类目集合。')
        output.update(monitorDim='cate',saleOrdCate3=deepcopy(ids))
    return output


def validate(report, values, day,*,archive=False):
    if report in METRIC_CONTRACTS:
        params(report,day,archive=archive)
        from .business_metrics import validate as metric_validate
        return metric_validate(report,values,day,archive=archive)
    expected=params(report, day,category={k:values.get(k) for k in ('firstIndId','secondIndId','thirdIndId')} if isinstance(values,dict) else None,
        shops={k:values.get(k) for k in ('selfShopId','compareShopId1')} if isinstance(values,dict) and report.startswith('compete-compare-') else None,
        products={k:values.get(k) for k in ('self'+CONTRACTS[report]['product_unit'].title()+'Id','compare'+CONTRACTS[report]['product_unit'].title()+'Id1')} if isinstance(values,dict) and CONTRACTS[report].get('requires_products') else None,
        target=(values.get(CONTRACTS[report]['target_field'],[None])[0] if CONTRACTS[report].get('target_array') and isinstance(values.get(CONTRACTS[report]['target_field']),list) and values[CONTRACTS[report]['target_field']] else values.get(CONTRACTS[report]['target_field'])) if isinstance(values,dict) and CONTRACTS[report].get('target_field') else None,
        page=values.get('pageNumber') if isinstance(values,dict) and report=='gift-money-activities' else 1,
        channel=values.get('channel') if isinstance(values,dict) and CONTRACTS[report].get('channel_options') else None,
        competition_category={'saleOrdCate3':values['saleOrdCate3']} if isinstance(values,dict) and 'saleOrdCate3' in values else None,archive=archive)
    # Equality alone accepts True as 1; preserve exact JSON types as well.
    if json.dumps(values,sort_keys=True,ensure_ascii=False)!=json.dumps(expected,sort_keys=True,ensure_ascii=False):
        raise ValueError('只读统计参数超出登记范围。')
    return expected


def choose_target(options,report,store,query=None):
    c=CONTRACTS[report]
    if c['target_kind']=='activity':
        rows=options.get('list') if isinstance(options,dict) else None
        if not isinstance(rows,list) or any(not isinstance(r,dict) or not re.fullmatch(r'[1-9]\d*',str(r.get('activityId',''))) for r in rows):raise ValueError('缺少官方礼金活动列表。')
        hits=rows[:1] if query is None else [r for r in rows if str(r['activityId'])==query]
        if len(hits)!=1:raise ValueError('须选择本次官方列表内唯一活动ID；未返回的活动不擅自代入。')
        target=str(hits[0]['activityId'])
    elif c['target_kind']=='shop':
        selected=choose_competitor(options,store,query)
        target=selected['params']['compareShopId1'][0]
    else:
        rows=options.get('data') if isinstance(options,dict) else None
        if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):raise ValueError('缺少官方监控商品字典。')
        if any(r.get('type')=='self' and str(r.get('shop_id'))!=store.removeprefix('jd:mall:') for r in rows):raise ValueError('监控字典本店不符。')
        candidates=[r for r in rows if r.get('type')=='compare' and r.get('disabled') is False]
        hits=candidates[:1] if query is None else [r for r in candidates if str(r.get('value'))==query]
        if len(hits)!=1:raise ValueError('须选择唯一已监控且可用的商品ID。')
        target=str(hits[0].get('value',''))
    if not re.fullmatch(r'[1-9]\d*',target):raise ValueError('监控对象ID无效。')
    return {'target':target,'kind':c['target_kind'],'selection':'first_official_monitored_target' if query is None else 'official_exact_monitored_target'}


def target_options(report):
    c=CONTRACTS[report]
    if c['target_kind']=='activity':return 'gift-money-activities'
    return 'compete-shop-options' if c['target_kind']=='shop' else 'compete-product-'+c['product_unit']+'-options'


def choose_products(options,unit,store,query=None):
    rows=options.get('data') if isinstance(options,dict) else None
    if unit not in ('sku','spu') or not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):raise ValueError('缺少官方竞品商品字典。')
    if any(r.get('type')=='self' and str(r.get('shop_id'))!=store.removeprefix('jd:mall:') for r in rows):raise ValueError('官方本品字典与绑定店铺不符。')
    if query is not None and (not isinstance(query,dict) or not set(query)<= {'self_id','compare_id'} or any(v is not None and (not isinstance(v,str) or not re.fullmatch(r'[1-9]\d*',v)) for v in query.values())):raise ValueError('本品/竞品ID筛选无效。')
    selected={}
    for kind,field in [('self','self'+unit.title()+'Id'),('compare','compare'+unit.title()+'Id1')]:
        hits=[r for r in rows if r.get('type')==kind and r.get('disabled') is False]
        wanted=(query or {}).get(kind+'_id')
        if wanted is not None:hits=[r for r in hits if str(r.get('value'))==wanted]
        if not hits or not re.fullmatch(r'[1-9]\d*',str(hits[0].get('value',''))):raise ValueError('官方字典缺少本品或已监控竞品，不自动添加配置。')
        if wanted is not None and len(hits)!=1:raise ValueError('官方商品ID筛选不唯一。')
        selected[field]=[str(hits[0]['value'])]
    if len({v[0] for v in selected.values()})!=2:raise ValueError('本品与竞品不能相同。')
    result={'params':selected,'selection':'first_official_self_and_monitored_competitor'}
    if query is not None:result.update(selection='official_supplied_ids_with_default_fallback',requested_ids=query)
    return result


def choose_competitor(options,store,query=None):
    rows=options.get('data') if isinstance(options,dict) else None
    if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows):raise ValueError('缺少官方已配置竞店字典。')
    own=[r for r in rows if r.get('type')=='self']
    if len(own)!=1 or str(own[0].get('value'))!=store.removeprefix('jd:mall:'):raise ValueError('竞店字典本店与绑定店铺不符。')
    others=[r for r in rows if r.get('type')=='compare' and r.get('disabled') is not True and str(r.get('value'))!=str(own[0]['value'])]
    hits=others[:1] if query is None else [r for r in others if str(r.get('value'))==str(query) or r.get('label')==query]
    if len(hits)!=1:raise ValueError('须选择唯一已配置竞店。')
    return {'params':{'selfShopId':[str(own[0]['value'])],'compareShopId1':[str(hits[0]['value'])]},
        'compare_name':hits[0].get('label'),'selection':'first_official_configured_competitor' if query is None else 'official_exact_match'}


def choose_competition_category(options,query):
    dims=options.get('data') if isinstance(options,dict) else None
    if not isinstance(dims,list):raise ValueError('缺少官方竞争类目字典。')
    roots=[d for d in dims if d.get('dimCode')=='saleOrdCate']
    if len(roots)!=1 or not isinstance(roots[0].get('dimVals'),list):raise ValueError('竞争类目字典不唯一。')
    hits=[]
    def visit(nodes,path):
        for node in nodes:
            if not isinstance(node,dict):raise ValueError('官方类目节点无效。')
            current=path+[node]
            if node.get('label')==query or str(node.get('value'))==query:hits.append(current)
            visit(node.get('children') or [],current)
    visit(roots[0]['dimVals'],[])
    if len(hits)!=1 or len(hits[0]) not in (1,2):raise ValueError('须唯一匹配官方二三级类目。')
    path=hits[0];node=path[-1];ids=[]
    if len(path)==1:
        for child in node.get('children') or []:
            if child.get('disabled') is False and not child.get('children'):ids.append(str(child.get('value','')))
    elif node.get('disabled') is False:ids=[str(node.get('value',''))]
    if not ids or any(not re.fullmatch(r'[1-9]\d*',x) for x in ids) or len(set(ids))!=len(ids):raise ValueError('该类目没有官方可选择的三级子类目。')
    return {'params':{'saleOrdCate3':ids},'path':[n['label'] for n in path],'category_id':str(node['value']),
        'selection':'official_enabled_children' if len(path)==1 else 'official_exact_third_category','selected_third_categories':len(ids)}


def choose_category(options, query=None):
    if not isinstance(options,dict) or not isinstance(options.get('category'),list):raise ValueError('缺少官方行业类目字典。')
    wanted=str(options.get('mainSecondIndId')) if query is None else str(query)
    hits=[]
    def visit(nodes,path):
        for node in nodes:
            if not isinstance(node,dict):raise ValueError('行业类目节点无效。')
            current=path+[node]
            if str(node.get('id'))==wanted or node.get('name')==wanted:hits.append(current)
            visit(node.get('children') or [],current)
    visit(options['category'],[])
    if len(hits)!=1 or len(hits[0]) not in (2,3):raise ValueError('须选择唯一官方二级或三级类目。')
    path=hits[0]
    if any(type(node.get('id')) is not int or node['id']<=0 or node['id']==999999 for node in path):raise ValueError('官方类目ID无效。')
    if query is None and path[0]['id']!=options.get('mainFirstIndId'):raise ValueError('官方主类目父子关系不符。')
    return {'params':{'firstIndId':path[0]['id'],'secondIndId':path[1]['id'],'thirdIndId':path[2]['id'] if len(path)==3 else 999999},
            'path':[node['name'] for node in path],'selection':'official_main_category' if query is None else 'official_exact_match'}


def url(report, values):
    c=CONTRACTS[report]
    if c['method']=='POST':return c['origin']+c['path']
    query=urlencode(sorted((k,str(v).lower() if isinstance(v,bool) else v) for k,v in values.items()))
    return c['origin']+c['path']+('?' + query if query else '')


def business_body(raw,report=None):
    if report in METRIC_CONTRACTS:
        from .user_metrics import business_body as metric_body
        return metric_body(raw)
    if not isinstance(raw,dict) or raw.get('errors'):
        raise ValueError('只读统计业务响应失败。')
    if 'header' in raw:
        code=raw.get('header',{}).get('code') if isinstance(raw.get('header'),dict) else None
        if type(code) not in (int,str) or str(code)!='0' or not isinstance(raw.get('body'),dict):
            raise ValueError('只读统计header或body失败，权限和风控不能当空数据。')
        return deepcopy(raw['body'])
    status_ok=type(raw.get('status')) is int and raw['status']==0
    if report=='compete-overview-keywords' and type(raw.get('status')) is str and raw['status']=='0':status_ok=True
    if not status_ok or not isinstance(raw.get('content'),(dict,list)):
        raise ValueError('只读统计status或content失败，缺失不能当空表。')
    return deepcopy(raw['content'])


def _indexed_rows(data, indices):
    if not isinstance(data,list) or not isinstance(indices,dict) or not indices or any(type(i) is not int or i<0 for i in indices.values()):raise ValueError('统计表列索引无效。')
    if any(not isinstance(row,list) or max(indices.values())>=len(row) for row in data):raise ValueError('统计表行宽与索引不符。')
    return data


def _chart(data,*,flat=False):
    if not isinstance(data,dict) or not isinstance(data.get('series'),list):raise ValueError('统计图序列无效。')
    if 'categories' in data:
        if not isinstance(data['categories'],list):raise ValueError('统计图分类无效。')
        if flat:
            if len(data['series'])!=len(data['categories']) or any(v is not None and type(v) not in (int,float) for v in data['series']):raise ValueError('统计图单序列与分类不符。')
        elif any(not isinstance(s,dict) or not isinstance(s.get('data'),list) or len(s['data'])!=len(data['categories']) for s in data['series']):raise ValueError('统计图序列与分类不符。')
    elif any(not isinstance(s,list) or len(s)!=2 for s in data['series']):raise ValueError('统计图标签值序列不符。')


def _new_observed(data,report,coverage,day):
    """Schemas actually returned by 0.9.29, preserving source indices and gaps."""
    rows=None
    if report.startswith('content-detail-') and report.endswith(('-contents','-sources','-products')):
        table=data.get('data') if isinstance(data,dict) and report.endswith(('-sources','-products')) else data
        if not isinstance(table,dict):raise ValueError('内容明细表结构无效。')
        rows=_indexed_rows(table.get('data'),table.get('metaIndex'))
        coverage.update(all_available_rows_complete=False,hit_observed_1000_row_limit=len(rows)==1000,
            note=coverage['note']+' 内容及商品列表已观察到1000行上限，未证明全量；当日、7日和15日引导成交窗口分别保留，不能相加。')
    elif report=='content-detail-subtypes':
        if not isinstance(data,dict) or not isinstance(data.get('channel'),list) or not isinstance(data.get('initItem'),dict) or any(not isinstance(x,dict) or not isinstance(x.get('code'),str) or not isinstance(x.get('name'),str) for x in data['channel']) or data['initItem'] not in data['channel']:raise ValueError('内容子类型选项结构无效。')
        rows=data['channel']
    elif report in ('compete-monitor-product-count','compete-monitor-shop-count'):
        rows=data.get('data') if isinstance(data,dict) else None
        if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict) or any(type(rows[0].get(k)) is not int or rows[0][k]<0 for k in ('curCount','totalCount')):raise ValueError('监控数量结构无效。')
        coverage.update(metadata_only=True,current_monitored=rows[0]['curCount'],monitoring_limit=rows[0]['totalCount'],over_limit=rows[0]['curCount']>rows[0]['totalCount'])
    elif report in ('compete-shop-filters','compete-monitor-filters','compete-shop-dates'):
        if not isinstance(data,dict):raise ValueError('竞店页面元数据结构无效。')
        if report.endswith('-filters'):
            rows=data.get('data')
            if not isinstance(rows,list) or not rows or any(not isinstance(r,dict) or not isinstance(r.get('dimCode'),str) or not isinstance(r.get('dimVals'),list) for r in rows):raise ValueError('竞店筛选字典无效。')
        else:
            if not isinstance(data.get('data'),dict) or not data['data']:raise ValueError('竞店页面选项无效。')
            coverage.update(date_availability_provided=False,metadata_kind='page_flags',
                note=coverage['note']+' 兼容命令名dates实际返回页面开关，sznMaxAge不是业务日期可用边界。')
    elif report=='compete-realtime-trend':
        if not isinstance(data,dict) or not isinstance(data.get('series'),list) or not data['series'] or any(not isinstance(s,dict) or s.get('code') not in ('self','competitor') or not isinstance(s.get('data'),list) or not 0<len(s['data'])<=24 for s in data['series']):raise ValueError('实时竞争序列结构无效。')
        if len({len(s['data']) for s in data['series']})!=1 or len({s['code'] for s in data['series']})!=len(data['series']):raise ValueError('实时竞争序列长度或标识不符。')
        if data.get('categories')!=[f'{h:02}' for h in range(24)]:raise ValueError('实时竞争小时槽位缺失、重复或无序。')
        rows=[{'value':v} for s in data['series'] for v in s['data']]
        coverage.update(full_day_complete=False,returned_hour_slots=24,current_snapshot=True,
            returned_values_per_series=len(data['series'][0]['data']),unreturned_slots_not_zero_filled=True,
            note=coverage['note']+' 24个小时槽可多于实际序列长度，不补齐未返回时段，当前小时未结算，不代表完整日数据。')
    elif report in ('compete-overview-summary','compete-realtime-summary'):
        if not isinstance(data,dict) or any(type(data.get(k)) is not int or data[k]<0 for k in ('shopNum','totalShopNum')):raise ValueError('竞店概览计数无效。')
        if report=='compete-realtime-summary':
            stamp=data.get('realTime')
            if not isinstance(stamp,str):raise ValueError('实时竞争快照缺少源时间。')
            snapshot=datetime.strptime(stamp,'%Y-%m-%d %H:%M:%S')
            if day and snapshot.date().isoformat()!=day:raise ValueError('实时竞争快照源日期与归档不符。')
            coverage.update(source_snapshot_time=stamp,source_timezone='Asia/Shanghai',full_day_complete=False,current_snapshot=True)
        rows=[v for k,v in data.items() if k not in ('shopNum','totalShopNum','realTime')]
        if not rows or any(not isinstance(v,dict) or not {'self','competitor'}<=v.keys() for v in rows):raise ValueError('竞店核心指标对比结构无效。')
        coverage.update(indexation_fields_preserved=True,configured_competitor_count=data['shopNum'])
    elif report in ('compete-overview-shops','compete-overview-products','compete-overview-sources','compete-overview-keywords','compete-loss-shops','compete-loss-products','compete-realtime-shops','compete-realtime-products','compete-realtime-sources','compete-loss-product-list','compete-search-list'):
        if not isinstance(data,dict):raise ValueError('竞争明细表结构无效。')
        rows=_indexed_rows(data.get('data'),data.get('metaIndex'))
        coverage.update(indexation_fields_preserved=True,all_available_rows_complete=False,
            note=coverage['note']+' 竞店区间对象和官方median原样保留，不使用median冒充精确数据；返回明细不代表全部竞争商品/来源。')
        if report in ('compete-loss-product-list','compete-search-list'):coverage.update(hit_observed_1000_row_limit=len(rows)==1000,official_behavioral_loss_not_refund=report=='compete-loss-product-list')
        if report.startswith('compete-realtime-'):coverage.update(current_snapshot=True,full_day_complete=False)
    elif report=='compete-loss-summary':
        fields=('CartedSkipCustNum','DircetSkipCustNum','CollectedSkipCustNum','LossOrdCustNum','LossOrdAmt','CauseLossShopNum')
        if not isinstance(data,dict) or any(not isinstance(data.get(k),dict) or not {'value','rate'}<=data[k].keys() for k in fields):raise ValueError('竞争流失概览结构无效。')
        rows=[data[k] for k in fields]
        coverage['official_behavioral_loss_not_refund']=True
    elif report in ('coupon-share-summary','shop-gift-summary','expansion-money-trend'):
        if data!=[]:raise ValueError('该查询目前只核验官方空数组；非空结构待核验，不能静默放行。')
        rows=[];coverage['verified_shape_scope']='official_empty_array_only'
    elif report in ('gift-money-summary','expansion-money-summary'):
        if not isinstance(data,list) or any(not isinstance(g,dict) or not isinstance(g.get('code'),str) or not isinstance(g.get('items'),list) for g in data):raise ValueError('促销概览分组无效。')
        rows=[item for g in data for item in g['items']]
        if any(not isinstance(r,dict) or not isinstance(r.get('index'),str) or 'value' not in r for r in rows):raise ValueError('促销概览指标无效。')
        if rows and all(r['value'] in (None,'--','') for r in rows):coverage['data_availability']='all_values_missing'
    elif report in ('coupon-share-trend','shop-gift-trend','gift-money-trend','industry-sellers-joined-trend'):
        charts=data if report=='gift-money-trend' else [data]
        if not isinstance(charts,list):raise ValueError('促销趋势分组无效。')
        for chart in charts:
            _chart(chart)
            labels=chart.get('categories')
            if not isinstance(labels,list) or any(not isinstance(x,str) for x in labels):raise ValueError('趋势日期标签无效。')
            if labels:
                short=all(re.fullmatch(r'\d{2}-\d{2}',x) for x in labels)
                full=all(re.fullmatch(r'\d{4}-\d{2}-\d{2}',x) for x in labels)
                if not (short or full) or len(set(labels))!=len(labels):raise ValueError('趋势日期标签混合或重复。')
                for label in labels:date.fromisoformat(('2000-' if short else '')+label)
                if day and labels[-1]!=(day[-5:] if short else day):raise ValueError('趋势日期标签末日不符。')
                coverage.update(date_label_start=labels[0],date_label_end=labels[-1],date_year_explicit=full,returned_date_labels=len(labels))
            coverage['series_count']=coverage.get('series_count',0)+len(chart['series'])
        rows=[{'value':v} for chart in charts for s in chart['series'] for v in s['data']]
        coverage['actual_window_from_source']=True
    elif report in ('coupon-share-activities','shop-gift-activities','gift-money-activities'):
        if not isinstance(data,dict) or any(type(data.get(k)) is not int or data[k]<0 for k in ('pageCount','totalCount','pageNumber','pageSize')) or not 1<=data['pageNumber']<=max(1,data['pageCount']) or data['pageSize']<=0 or not isinstance(data.get('list'),list) or any(not isinstance(r,dict) for r in data['list']):raise ValueError('促销活动分页结构无效。')
        rows=data['list'];total=data['totalCount'];size=data['pageSize']
        if len(rows)>size or len(rows)>total or data['pageCount']!=(total+size-1)//size:raise ValueError('促销活动总数和分页不符。')
        coverage.update(official_total=total,page_count=data['pageCount'],page_number=data['pageNumber'],page_size=size,pagination_complete=len(rows)==total)
    elif report.startswith('industry-sellers-'):
        if not isinstance(data,dict):raise ValueError('行业卖家统计结构无效。')
        rows=_indexed_rows(data.get('data'),data.get('metaIndex'))
    elif report=='industry-buyers-filters':
        if not isinstance(data,dict) or not all(k in data for k in ('gender','price','range','region','age','metaIndex')):raise ValueError('行业人群选项缺失。')
        rows=[row for key in ('gender','price','range','region','age') for row in _indexed_rows(data[key],data['metaIndex'])]
    elif report=='industry-buyers-preference':
        if not isinstance(data,dict):raise ValueError('行业偏好结构无效。')
        rows=[row for key in ('cate','brand') for row in _indexed_rows(data.get(key),data.get('metaIndex'))]
        coverage['indexation_fields_preserved']=True
    elif report in ('industry-buyers-profile','industry-buyers-behaviour','industry-buyers-consumption'):
        if not isinstance(data,dict):raise ValueError('行业买家统计结构无效。')
        tables,charts={'industry-buyers-profile':(('cityRank','provRank'),('custProfession','custLevel')),
            'industry-buyers-behaviour':(('keyword',),('buy','promoteSensi','payment','ordTime','commentSensi')),
            'industry-buyers-consumption':((),('buyFreq','dealAmt'))}[report]
        for key in tables:
            table=data.get(key)
            if not isinstance(table,dict):raise ValueError('行业买家明细表缺失。')
            _indexed_rows(table.get('data'),table.get('metaIndex'))
        for key in charts:_chart(data.get(key),flat=key=='custLevel')
        if report=='industry-buyers-behaviour':
            if not isinstance(data.get('attr'),list) or any(not isinstance(g,dict) or not isinstance(g.get('title'),str) or not isinstance(g.get('attrs'),list) or any(not isinstance(a,dict) or 'name' not in a or 'DealCustRate' not in a for a in g['attrs']) for g in data['attr']):raise ValueError('行业购买属性结构无效。')
        coverage.update(validated_tables=list(tables),validated_charts=list(charts))
    else:return False
    coverage['schema_validation']='live_observed_structure_verified'
    if rows is not None:
        coverage['returned_rows']=len(rows)
        coverage.setdefault('data_availability','returned_values' if rows else 'empty_rows')
    return True


def normalize(raw, report, *, day=None, store=None,values=None):
    if report not in CONTRACTS:raise ValueError('未登记的统计响应。')
    if report in METRIC_CONTRACTS:
        from .business_metrics import parse as metric_parse
        return metric_parse(raw,report,day,values=values)
    data=business_body(raw,report)
    coverage={'scope':CONTRACTS[report]['scope'],
        'whole_module_complete':False,'nulls_preserved':True,'precise_values_inferred':False,
        'schema_validation':'official_wrapper_only_pending_live_schema',
        'note':'保留官方区间、指数、空值和趋势窗口；当前列表/元数据的date仅为归档日期。返回列表不代表全历史全量。'}
    times=[];rows=None
    if CONTRACTS[report].get('schema')=='realtime_config_pending':
        rows=data.get('data') if isinstance(data,dict) else None
        maximum=data.get('maxNum') if isinstance(data,dict) else None
        if not isinstance(rows,list) or type(maximum) is not int or maximum<0:raise ValueError('实时配置列表或容量无效。')
        for r in rows:
            if not isinstance(r,dict) or not isinstance(r.get('CompeteShopId'),str) or not r['CompeteShopId'].isdigit() or not isinstance(r.get('CompeteShopName'),str):raise ValueError('实时配置竞店身份无效。')
            if type(r.get('isFllowEachOther')) is not bool or type(r.get('indexShopFlag')) is not bool or type(r.get('isFllowedNum')) is not int or r['isFllowedNum']<0:raise ValueError('实时配置关注字段无效。')
            datetime.strptime(r['FollowTime'],'%Y-%m-%d %H:%M:%S')
        if len({r['CompeteShopId'] for r in rows})!=len(rows):raise ValueError('实时配置竞店重复。')
        coverage.update(metadata_only=True,configuration_modified=False,current_monitored=len(rows),monitoring_limit=maximum,remaining_capacity=max(0,maximum-len(rows)),native_visible_fields_verified=['CompeteShopId','CompeteShopName','FollowTime','isFllowEachOther','isFllowedNum'])
    elif CONTRACTS[report].get('schema')=='configuration_read_pending':
        rows=data.get('data') if isinstance(data,dict) else None
        maximum=data.get('other',{}).get('maxNum') if isinstance(data,dict) else None
        if not isinstance(rows,list) or type(data.get('size')) is not int or data['size']<0 or type(maximum) is not int or maximum<0:raise ValueError('竞争配置只读列表或容量结构不符。')
        keys=[]
        for r in rows:
            if not isinstance(r,dict) or not isinstance(r.get('monitorId'),str) or not r['monitorId'].isdigit():raise ValueError('竞争配置监控ID无效。')
            datetime.strptime(r['addTime'],'%Y-%m-%d %H:%M:%S')
            if report.endswith('-products'):
                if r.get('proType') not in ('sku','spu') or not isinstance(r.get('proId'),str) or not r['proId'].isdigit():raise ValueError('配置竞品类型或ID无效。')
                keys.append((r['proType'],r['monitorId']))
            else:
                if not isinstance(r.get('shopId'),str) or not r['shopId'].isdigit() or not isinstance(r.get('shopName'),str):raise ValueError('配置竞店ID或名称无效。')
                keys.append(r['monitorId'])
        if len(set(keys))!=len(keys):raise ValueError('配置列表重复监控对象。')
        coverage.update(metadata_only=True,configuration_modified=False,current_monitored=len(rows),monitoring_limit=maximum,remaining_capacity=max(0,maximum-len(rows)),official_size=data['size'],size_is_not_assumed_row_total=True)
    elif CONTRACTS[report].get('schema')=='gift_detail_pending':
        if not isinstance(values,dict):raise ValueError('礼金详情须绑定官方活动与原查询。')
        validate(report,values,day,archive=True)
        coverage.update(selected_activity=values['activityId'],activity_selection_scope='official_current_first_page',all_available_rows_complete=False,whole_query_complete=False,
            note=coverage['note']+' 活动概览为活动累计，商品表默认仅首页10条；不能当归档日业绩。')
        if report.endswith('-info'):
            if not isinstance(data,dict) or data.get('activityId')!=values['activityId'] or not isinstance(data.get('activityName'),str) or not isinstance(data.get('shopId'),str) or store and data['shopId']!=store.removeprefix('jd:mall:'):raise ValueError('礼金基础信息活动或店铺身份不符。')
            for key in ('actBeginTm','actEndTm'):datetime.strptime(data[key],'%Y-%m-%d %H:%M:%S')
            if data['actBeginTm']>data['actEndTm']:raise ValueError('礼金活动时间倒置。')
            rows=[data];coverage.update(metadata_only=True,activity_start=data['actBeginTm'],activity_end=data['actEndTm'])
        elif report.endswith(('-overview','-daily')):
            if not isinstance(data,list) or any(not isinstance(r,dict) or not isinstance(r.get('index'),str) or 'count' not in r for r in data):raise ValueError('礼金详情指标结构不符。')
            if [r['index'] for r in data]!=values['filterPropertys']:raise ValueError('礼金详情指标列表与请求不符。')
            rows=data;coverage['data_availability']='all_values_missing' if all(r['count'] in (None,'','--') for r in rows) else 'returned_values'
            coverage['metric_scope']='activity_lifetime' if report.endswith('-overview') else 'requested_day'
        elif report.endswith('-trend'):
            if data!=[]:raise ValueError('礼金详情趋势目前仅核验官方空结果，非空结构待有效样本。')
            rows=[];coverage['verified_shape_scope']='official_empty_array_only'
        else:
            if not isinstance(data,dict) or any(type(data.get(k)) is not int or data[k]<0 for k in ('pageCount','totalCount','pageNumber','pageSize')) or not isinstance(data.get('list'),list):raise ValueError('礼金商品分页结构无效。')
            rows=data['list'];total=data['totalCount'];size=data['pageSize']
            if size!=10 or data['pageNumber']!=1 or data['pageCount']!=(total+size-1)//size or len(rows)!=min(total,size):raise ValueError('礼金商品首分页数量不符。')
            if any(not isinstance(r,dict) or not isinstance(r.get('skuId'),str) or not re.fullmatch(r'[1-9]\d*',r['skuId']) for r in rows) or len({r['skuId'] for r in rows})!=len(rows):raise ValueError('礼金商品SKU缺失或重复。')
            coverage.update(official_total=total,page_count=data['pageCount'],page_size=size,page_number=1,pagination_complete=len(rows)==total,metric_scope='activity_lifetime_products')
    elif CONTRACTS[report].get('schema')=='monitor_pending':
        if not isinstance(values,dict):raise ValueError('竞争概况返回须绑定原查询。')
        validate(report,values,day,archive=True)
        rows=data.get('data') if isinstance(data,dict) else None
        if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows) or type(data.get('size')) is not int or data['size']<0:raise ValueError('竞争概况表结构无效。')
        requested=set(values['indicators']);present=set().union(*(r.keys() for r in rows)) if rows else set()
        coverage.update(indexation_fields_preserved=True,all_available_rows_complete=False,
            official_size=data['size'],size_is_not_assumed_row_total=True,
            missing_metric_columns=sorted(requested-present) if rows else [],
            note=coverage['note']+' 使用原查询绑定的全店或类目视角，不继承网页当前类目；缺失字段与null均不补零。')
        c=CONTRACTS[report];keys=[]
        if c.get('target_field'):coverage['selected_target']=values[c['target_field']]
        if report.endswith('-loss'):
            if rows or data['size']!=0:raise ValueError('流失下钻目前仅核验官方空表；非空结构待核验。')
            coverage.update(official_behavioral_loss_not_refund=True,verified_shape_scope='official_empty_array_only')
        elif report.endswith('-trend'):
            days=[r.get('dt') for r in rows]
            if any(not isinstance(d,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',d) or not values['startDate']<=d<=day for d in days):raise ValueError('监控趋势日期超出原查询。')
            keys=days;coverage.update(requested_start=values['startDate'],requested_end=day,requested_days=7,returned_days=len(set(days)),window_groups_complete=len(set(days))==7)
        elif report=='compete-monitor-shops':
            benchmark=[r for r in rows if r.get('type')=='market'];entities=[r for r in rows if r.get('type')!='market']
            if benchmark and (values.get('monitorDim')!='cate' or len(benchmark)!=1 or any(r.get('shopId') is not None for r in benchmark)):raise ValueError('竞店行业大盘行超出类目视角。')
            if any(r.get('type') not in ('self','compete') or not isinstance(r.get('shopId'),str) or not r['shopId'].isdigit() for r in entities):raise ValueError('监控店铺身份列无效。')
            if store and any(r['type']=='self' and r['shopId']!=store.removeprefix('jd:mall:') for r in entities):raise ValueError('监控店铺列表本店身份不符。')
            keys=[('market','benchmark')]*len(benchmark)+[('shop',r['shopId']) for r in entities];coverage.update(self_rows=sum(r['type']=='self' for r in entities),competitor_rows=sum(r['type']=='compete' for r in entities),benchmark_rows=len(benchmark),monitored_entity_rows=len(entities))
        else:
            field=c['product_unit']+'_id';benchmark=[r for r in rows if r.get('type')=='dapan'];entities=[r for r in rows if r.get('type')!='dapan']
            if benchmark and (values.get('monitorDim')!='cate' or len(benchmark)!=1 or any(r.get(field) is not None for r in benchmark)):raise ValueError('商品行业大盘行超出类目视角。')
            if any(not isinstance(r.get(field),str) or not r[field].isdigit() for r in entities):raise ValueError('监控商品ID列无效。')
            if report.endswith('-products') and any(r.get('type')!='detail' for r in entities):raise ValueError('监控商品行类型无效。')
            if c.get('target_kind')=='shop' and any(r.get('shop')!=values['shopId'] for r in entities):raise ValueError('竞店商品榜返回店铺不符。')
            keys=[('dapan','benchmark')]*len(benchmark)+[('product',r[field]) for r in entities]
            coverage.update(benchmark_rows=len(benchmark),monitored_entity_rows=len(entities))
            if report.endswith('-top'):coverage.update(ranking_only=True,observed_top_limit=10)
        if coverage.get('benchmark_rows') and not coverage.get('monitored_entity_rows'):coverage['data_availability']='no_monitored_entities_benchmark_only'
        if len(set(keys))!=len(keys):raise ValueError('监控统计分组重复。')
    elif CONTRACTS[report].get('schema')=='product_aux':
        if not isinstance(values,dict):raise ValueError('竞品辅助表须绑定已选择商品。')
        validate(report,values,day,archive=True)
        rows=data.get('data') if isinstance(data,dict) else None
        if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows) or type(data.get('size')) is not int:raise ValueError('竞品辅助表结构无效。')
        if report.endswith('-customers'):
            if data['size']!=-1 or rows:raise ValueError('客户画像目前仅核验官方低样本阈值空结构；非空结构待核验。')
            coverage.update(data_availability='official_audience_below_threshold',verified_shape_scope='official_suppressed_empty_only',schema_validation='live_observed_structure_verified',official_size=-1,returned_rows=0,
                note=coverage['note']+' 官方size=-1表示人群样本较小，暂无法生成画像；不是0人或0成交。')
            return {'data':data,'coverage':coverage}
        if data['size']<0:raise ValueError('竞品辅助表size无效。')
        unit=CONTRACTS[report]['product_unit'];field=unit+'_id';kind=unit.title();own=values['self'+kind+'Id'][0];other=values['compare'+kind+'Id1'][0]
        required=set(values['indicators'])
        if report.endswith('-sources') or CONTRACTS[report].get('source_level'):
            source=values['groups'][-1];required|={field,source}
            if any(r.get(field)!=own or r.get(field+'##compete1') is not None and r[field+'##compete1']!=other for r in rows):raise ValueError('来源返回本品或竞品ID不符。')
            keys=[r.get(source) for r in rows]
            peer=sum(r.get(field+'##compete1') is not None for r in rows)
            if any(r.get(field+'##compete1') is None and any(v is not None for k,v in r.items() if k.endswith('##compete1')) for r in rows):raise ValueError('商品来源缺少竞品身份但含竞品值。')
            coverage.update(source_level=CONTRACTS[report].get('source_level',1),source_parent_path=[values['flowSrcId'+str(n)][0] for n in range(1,CONTRACTS[report].get('source_level',1))],channel='app',counterpart_rows_returned=peer,counterpart_rows_missing=len(rows)-peer,
                comparison_side_complete=bool(rows) and peer==len(rows),requested_row_limit=values.get('pageSize'),hit_row_limit=len(rows)>=values['pageSize'] if 'pageSize' in values else False,note=coverage['note']+' 可能仅返回本品侧；未返回的竞品侧不补零。')
        else:
            keyword=values['groups'][0];required|={field,keyword}
            if any(r.get(field) not in (own,other) or not isinstance(r.get(keyword),str) for r in rows):raise ValueError('关键词商品ID或关键词列不符。')
            keys=[(r[field],r[keyword]) for r in rows]
            coverage.update(requested_row_limit=200,ranking_only=True,channel='app',
                note=coverage['note']+' 访客与成交排序可能返回不同候选集合，缺失成交值不当0；返回关键词不代表全部搜索词。')
        if any(not required<=r.keys() for r in rows):raise ValueError('竞品辅助表缺少本品指标。')
        if len(set(keys))!=len(keys):raise ValueError('竞品辅助表分组重复。')
        coverage.update(official_size=data['size'],size_is_not_assumed_row_total=True,indexation_fields_preserved=True,all_available_rows_complete=False)
    elif report.startswith('compete-product-'):
        rows=data.get('data') if isinstance(data,dict) else None
        if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows) or type(data.get('size')) is not int or data['size']<0:raise ValueError('竞品对比响应表结构无效。')
        if report.endswith('-options'):
            if any(r.get('type') not in ('self','compare') or type(r.get('disabled')) is not bool or not re.fullmatch(r'[1-9]\d*',str(r.get('value',''))) for r in rows):raise ValueError('竞品官方字典节点无效。')
            if store and any(r['type']=='self' and str(r.get('shop_id'))!=store.removeprefix('jd:mall:') for r in rows):raise ValueError('竞品官方字典本品店铺不符。')
            keys=[(r['type'],str(r['value'])) for r in rows]
            coverage.update(metadata_only=True,eligible_self=sum(r['type']=='self' and r['disabled'] is False for r in rows),eligible_monitored_competitors=sum(r['type']=='compare' and r['disabled'] is False for r in rows))
        else:
            if not isinstance(values,dict):raise ValueError('竞品响应须绑定已核验查询参数。')
            validate(report,values,day,archive=True)
            unit=CONTRACTS[report]['product_unit'];field=unit+'_id';kind=unit.title()
            allowed=set(values['self'+kind+'Id']+values['compare'+kind+'Id1'])
            if any(not isinstance(r.get(field),str) or r[field] not in allowed or not set(values['indicators'])<=r.keys() for r in rows):raise ValueError('竞品响应商品ID或指标超出原查询。')
            keys=[r[field] for r in rows]
            if report.endswith('-trend'):
                dates=[r.get('dt') for r in rows]
                if any(not isinstance(d,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',d) or not values['startDate']<=d<=day for d in dates):raise ValueError('竞品趋势日期超出原查询。')
                keys=[(r[field],r['dt']) for r in rows]
                coverage.update(requested_start=values['startDate'],requested_end=day,requested_days=30,window_groups_complete=len(set(keys))==60)
            coverage.update(indexation_fields_preserved=True,selected_products=sorted(allowed),precise_values_inferred=False,
                note=coverage['note']+' 本品与竞品均可能为官方区间，median不当精确值。')
        if len(set(keys))!=len(keys):raise ValueError('竞品响应分组重复。')
        coverage.update(official_size=data['size'],size_is_not_assumed_row_total=True,all_available_rows_complete=False)
    elif report.startswith('compete-compare-'):
        if not isinstance(values,dict):raise ValueError('新版竞店返回须绑定原查询参数。')
        validate(report,values,day,archive=True)
        rows=data.get('data') if isinstance(data,dict) else None
        if not isinstance(rows,list) or any(not isinstance(r,dict) for r in rows) or type(data.get('size')) is not int or data['size']<0:raise ValueError('新版竞店返回表结构不符。')
        allowed=set(values['selfShopId']+values['compareShopId1'])
        source_table=report=='compete-compare-sources' or bool(CONTRACTS[report].get('source_level'))
        if not source_table and any(not isinstance(r.get('shop'),str) or r['shop'] not in allowed for r in rows):raise ValueError('新版竞店响应包含未选择店铺。')
        required=set(values['indicators'])
        if report=='compete-compare-sources' or CONTRACTS[report].get('source_level'):
            field=values['groups'][0];required|={field}
            if any(r.get('shop') is not None and r['shop']!=values['selfShopId'][0] or r.get('shop##compete1') is not None and r['shop##compete1']!=values['compareShopId1'][0] or r.get('shop') is None and r.get('shop##compete1') is None for r in rows):raise ValueError('竞店来源的本店/竞店列不符。')
            own=sum(r.get('shop') is not None for r in rows)
            if any(r.get('shop') is None and any(r.get(m) is not None for m in values['indicators']) for r in rows):raise ValueError('来源缺少本店身份但含本店值。')
            peer=sum(r.get('shop##compete1') is not None for r in rows)
            peer_required={field+'##compete1'}|{m+'##compete1' for m in values['indicators']}
            if any(r.get('shop##compete1') is not None and (not peer_required<=r.keys() or r[field+'##compete1']!=r[field]) for r in rows):raise ValueError('竞店来源的已返回竞品字段或来源ID不符。')
            if any(r.get('shop##compete1') is None and any(v is not None for k,v in r.items() if k.endswith('##compete1')) for r in rows):raise ValueError('竞店来源缺少身份但含竞店数值。')
            coverage.update(self_rows_returned=own,self_rows_missing=len(rows)-own,counterpart_rows_returned=peer,counterpart_rows_missing=len(rows)-peer,comparison_side_complete=bool(rows) and peer==len(rows) and own==len(rows),note=coverage['note']+' 未返回的本店或竞店来源侧不补零。')
            keys=[r.get(field) for r in rows]
            coverage.update(source_level=CONTRACTS[report].get('source_level',1),source_parent_path=[values['flowSrcId'+str(n)][0] for n in range(1,CONTRACTS[report].get('source_level',1))],channel='app',requested_row_limit=1000,all_available_rows_complete=False)
        elif report=='compete-compare-summary':keys=[r['shop'] for r in rows]
        elif report=='compete-compare-trend':
            required.add('dt');keys=[(r['shop'],r.get('dt')) for r in rows]
            dates=[r.get('dt') for r in rows]
            if any(not isinstance(d,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',d) or not values['startDate']<=d<=day for d in dates):raise ValueError('竞店趋势返回日期超出官方窗口。')
            expected={(s,(date.fromisoformat(day)-timedelta(days=n)).isoformat()) for s in allowed for n in range(7)}
            coverage.update(requested_start=values['startDate'],requested_end=day,requested_days=7,returned_shop_date_groups=len(set(keys)),requested_shop_date_groups=len(expected),window_groups_complete=set(keys)==expected)
        else:
            unit=values['proType']+'_id';required|={unit,'rank'};keys=[(r['shop'],r.get(unit)) for r in rows]
            if any(not isinstance(r.get(unit),str) or not re.fullmatch(r'\d+',r[unit]) or type(r.get('rank')) is not int or r['rank']<1 for r in rows):raise ValueError('竞店商品榜ID或排名无效。')
            coverage.update(ranking_only=True,all_available_rows_complete=False,rows_per_shop={s:sum(r['shop']==s for r in rows) for s in sorted(allowed)})
        if any(not required<=r.keys() for r in rows):raise ValueError('新版竞店返回缺少已登记指标或分组。')
        if len(set(keys))!=len(keys):raise ValueError('新版竞店返回重复分组。')
        coverage.update(indexation_fields_preserved=True,official_size=data['size'],size_is_not_assumed_row_total=True,
            requested_comparison_window=[values['compareStartDate'],values['compareEndDate']],
            comparison_values_inferred=False,note=coverage['note']+' 本店及竞店均可能为官方区间，不将median作为精确值；请求了比较窗口不等于返回了比较期指标。')
    elif report in ('marketing-summary','content-summary') or report.startswith('content-detail-') and report.endswith('-summary'):
        if not isinstance(data,list) or any(not isinstance(group,dict) or not isinstance(group.get('code'),str) or not isinstance(group.get('summaryItems'),list) for group in data):raise ValueError('概览分组结构不符。')
        rows=[item for group in data for item in group['summaryItems']]
        if any(not isinstance(item,dict) or not isinstance(item.get('index'),str) or 'value' not in item for item in rows):raise ValueError('概览指标结构不符。')
    elif report.endswith('-filter-options') and report.startswith('tool-'):
        keys=('peopleList','platformList','typeList')
        if not isinstance(data,dict) or any(not isinstance(data.get(k),list) or any(not isinstance(r,dict) or type(r.get('id')) not in (str,int) or not isinstance(r.get('name'),str) for r in data[k]) or len({str(r['id']) for r in data[k]})!=len(data[k]) for k in keys):raise ValueError('促销筛选字典结构无效。')
        rows=[r for k in keys for r in data[k]];coverage.update(metadata_only=True,option_counts={k:len(data[k]) for k in keys},server_filtering_supported=False,note=coverage['note']+' 字典用于解释官方选项；原生列表为返回后本地筛选，不推断新增服务端参数。')
    elif report.startswith('tool-') and report.endswith('-summary'):
        if not isinstance(data,dict) or not isinstance(data.get('summary'),list) or not isinstance(data.get('description'),list):raise ValueError('工具效果概览结构不符。')
        rows=data['summary']
        if any(not isinstance(item,dict) or not isinstance(item.get('index'),str) or 'value' not in item for item in rows):raise ValueError('工具效果指标结构不符。')
    elif report in ('marketing-trend','content-trend','compete-loss-trend') or report.startswith('content-detail-') and report.endswith('-trend'):
        if not isinstance(data,dict) or not isinstance(data.get('categories'),list) or not isinstance(data.get('series'),list):raise ValueError('趋势序列结构不符。')
        times=data['categories']
        if any(not isinstance(series,dict) or not isinstance(series.get('data'),list) or len(series['data'])!=len(times) for series in data['series']):raise ValueError('趋势日期和序列长度不符。')
        coverage['series_count']=len(data['series'])
        rows=[{'value':v} for series in data['series'] for v in series['data']]
    elif report.startswith(('subsidy-','cross-sell-')) or report=='compete-shop-options':
        if not isinstance(data,dict) or not isinstance(data.get('data'),list) or type(data.get('size')) is not int or data['size']<0 or any(not isinstance(row,dict) for row in data['data']):raise ValueError('统计表数据或size结构不符。')
        rows=data['data'];coverage.update(official_size=data['size'],returned_rows=len(rows),size_is_not_assumed_row_total=True)
        if report.endswith('-trend'):
            field='dt' if report.startswith('subsidy-') else 'DT'
            if any(field not in row for row in rows):raise ValueError('趋势缺少日期。')
            times=[row[field] for row in rows]
            coverage['metric_rows']=sum(any(v is not None for k,v in row.items() if k not in (field,'shop_id')) for row in rows)
        if store and any('shop_id' in row and str(row['shop_id'])!=store.removeprefix('jd:mall:') for row in rows):raise ValueError('统计行店铺不符。')
    elif report.endswith('-activities') and report.startswith('tool-') or report=='content-types':
        if not isinstance(data,dict) or not isinstance(data.get('data'),list) or not isinstance(data.get('metaIndex'),dict):raise ValueError('官方动态指标表结构不符。')
        rows=data['data']
        if any(not isinstance(row,list) for row in rows) or any(type(index) is not int or index<0 or any(index>=len(row) for row in rows) for index in data['metaIndex'].values()):raise ValueError('官方指标列索引不符。')
        coverage['returned_rows']=len(rows)
    elif report=='industry-buyers-options':
        if not isinstance(data,dict) or not isinstance(data.get('category'),list) or 'mainSecondIndId' not in data:raise ValueError('行业类目字典结构不符。')
    else:
        _new_observed(data,report,coverage,day)
        return {'data':data,'coverage':coverage}
    coverage['schema_validation']='live_observed_structure_verified'
    if rows is not None:
        coverage.setdefault('returned_rows',len(rows))
        coverage.setdefault('data_availability','empty_rows' if not rows else 'returned_values')
        if report in ('marketing-summary','content-summary') or report.startswith('tool-') and report.endswith('-summary'):
            coverage['data_availability']='all_values_null' if rows and all(row['value'] is None for row in rows) else coverage['data_availability']
        if report=='subsidy-summary' and rows and all(all(v is None for v in row.values()) for row in rows):coverage['data_availability']='all_values_null'
    if times:
        dates=[]
        for value in times:
            if not isinstance(value,str) or not re.fullmatch(r'\d{8}|\d{4}-\d{2}-\d{2}',value):raise ValueError('趋势日期无效。')
            dates.append(datetime.strptime(value,'%Y%m%d' if len(value)==8 else '%Y-%m-%d').date())
        coverage.update(returned_start=min(dates).isoformat(),returned_end=max(dates).isoformat(),unique_dates=len(set(dates)),
            duplicate_dates=len(dates)-len(set(dates)),missing_days_within_span=(max(dates)-min(dates)).days+1-len(set(dates)))
        if day and coverage['returned_end']!=day:raise ValueError('趋势末日与请求日期不符。')
        if coverage['duplicate_dates']:raise ValueError('趋势日期重复。')
    return {'data':data,'coverage':coverage}


LIVE_VERIFIED_20261027=frozenset(['marketing-summary', 'marketing-trend', 'tool-single-summary', 'tool-single-activities', 'tool-suit-summary', 'tool-suit-activities', 'tool-total-summary', 'tool-total-activities', 'tool-shop-summary', 'tool-shop-activities', 'tool-product-summary', 'tool-product-activities', 'content-summary', 'content-trend', 'content-types', 'subsidy-summary', 'subsidy-trend', 'subsidy-products', 'industry-buyers-options', 'industry-buyers-filters', 'industry-buyers-profile', 'industry-buyers-behaviour', 'industry-buyers-consumption', 'industry-buyers-preference', 'cross-sell-summary', 'cross-sell-trend', 'cross-sell-activities', 'industry-sellers-provinces', 'industry-sellers-cities', 'industry-sellers-categories', 'industry-sellers-joined-trend', 'compete-shop-options', 'shop-gift-summary', 'shop-gift-trend', 'coupon-share-summary', 'coupon-share-trend', 'coupon-share-activities', 'shop-gift-activities', 'gift-money-summary', 'gift-money-trend', 'gift-money-activities', 'expansion-money-summary', 'expansion-money-trend', 'brand-card-member-overall', 'brand-card-member-shop', 'brand-card-shop', 'rating-gift-summary', 'rating-gift-trend', 'bunding-sale-summary', 'bunding-sale-trend', 'content-realtime-summary', 'content-realtime-hourly', 'content-realtime-sku', 'brand-card-member-overall-shop-new', 'brand-card-member-overall-card-new', 'brand-card-member-overall-tier-top10', 'brand-card-member-shop-shop-new', 'brand-card-member-shop-card-new', 'brand-card-shop-shop-new', 'brand-card-shop-card-new', 'brand-card-shop-tier-top10', 'rating-gift-activities', 'bunding-sale-products', 'compete-overview-summary', 'compete-overview-shops', 'compete-overview-products', 'compete-overview-sources', 'compete-overview-keywords', 'compete-loss-summary', 'compete-loss-trend', 'compete-loss-shops', 'compete-loss-products', 'content-detail-article-summary', 'content-detail-article-trend', 'content-detail-article-contents', 'content-detail-article-sources', 'content-detail-article-products', 'content-detail-video-summary', 'content-detail-video-trend', 'content-detail-video-contents', 'content-detail-video-sources', 'content-detail-video-products', 'content-detail-live-summary', 'content-detail-live-trend', 'content-detail-live-contents', 'content-detail-live-sources', 'content-detail-live-products', 'content-detail-subtypes', 'compete-realtime-summary', 'compete-realtime-trend', 'compete-realtime-shops', 'compete-realtime-products', 'compete-realtime-sources', 'compete-loss-product-list', 'compete-search-list', 'compete-shop-filters', 'compete-shop-dates', 'compete-compare-summary', 'compete-compare-trend', 'compete-compare-sku-trade', 'compete-compare-sku-flow', 'compete-compare-spu-trade', 'compete-compare-spu-flow', 'compete-compare-sources', 'compete-product-spu-options', 'compete-product-spu-summary', 'compete-product-spu-trend', 'compete-product-sku-options', 'compete-product-sku-summary', 'compete-product-sku-trend', 'compete-product-sku-core-all', 'compete-product-sku-sources', 'compete-product-sku-keywords-flow', 'compete-product-sku-keywords-deal', 'compete-product-sku-customers', 'compete-product-spu-core-all', 'compete-product-spu-sources', 'compete-product-spu-keywords-flow', 'compete-product-spu-keywords-deal', 'compete-product-spu-customers', 'compete-monitor-product-count', 'compete-monitor-shop-count', 'compete-monitor-filters', 'compete-monitor-sku-products', 'compete-monitor-sku-trend', 'compete-monitor-sku-loss', 'compete-monitor-shop-sku-top', 'compete-monitor-spu-products', 'compete-monitor-spu-trend', 'compete-monitor-spu-loss', 'compete-monitor-shop-spu-top', 'compete-monitor-shops', 'compete-monitor-shop-trend', 'compete-compare-sources-level2', 'compete-compare-sources-level3', 'compete-product-sku-sources-level2', 'compete-product-sku-sources-level3', 'compete-product-spu-sources-level2', 'compete-product-spu-sources-level3', 'tool-single-filter-options', 'tool-total-filter-options', 'gift-money-detail-info', 'gift-money-detail-overview', 'gift-money-detail-daily', 'gift-money-detail-trend', 'gift-money-detail-products', 'compete-config-products', 'compete-config-shops', 'compete-realtime-config-shops'])


LIVE_VERIFIED_DATES={'marketing-summary': '2026-10-26', 'marketing-trend': '2026-10-26', 'tool-single-summary': '2026-10-26', 'tool-single-activities': '2026-10-26', 'tool-suit-summary': '2026-10-26', 'tool-suit-activities': '2026-10-26', 'tool-total-summary': '2026-10-26', 'tool-total-activities': '2026-10-26', 'tool-shop-summary': '2026-10-26', 'tool-shop-activities': '2026-10-26', 'tool-product-summary': '2026-10-26', 'tool-product-activities': '2026-10-26', 'content-summary': '2026-10-26', 'content-trend': '2026-10-26', 'content-types': '2026-10-26', 'subsidy-summary': '2026-10-26', 'subsidy-trend': '2026-10-26', 'subsidy-products': '2026-10-26', 'industry-buyers-options': '2026-10-27', 'industry-buyers-filters': '2026-10-27', 'industry-buyers-profile': '2026-10-27', 'industry-buyers-behaviour': '2026-10-27', 'industry-buyers-consumption': '2026-10-27', 'industry-buyers-preference': '2026-10-27', 'cross-sell-summary': '2026-10-26', 'cross-sell-trend': '2026-10-26', 'cross-sell-activities': '2026-10-26', 'industry-sellers-provinces': '2026-10-27', 'industry-sellers-cities': '2026-10-27', 'industry-sellers-categories': '2026-10-27', 'industry-sellers-joined-trend': '2026-10-27', 'compete-shop-options': '2026-10-26', 'shop-gift-summary': '2026-10-26', 'shop-gift-trend': '2026-10-26', 'coupon-share-summary': '2026-10-26', 'coupon-share-trend': '2026-10-26', 'coupon-share-activities': '2026-10-26', 'shop-gift-activities': '2026-10-26', 'gift-money-summary': '2026-10-26', 'gift-money-trend': '2026-10-26', 'gift-money-activities': '2026-10-27', 'expansion-money-summary': '2026-10-26', 'expansion-money-trend': '2026-10-26', 'brand-card-member-overall': '2026-10-26', 'brand-card-member-shop': '2026-10-26', 'brand-card-shop': '2026-10-26', 'rating-gift-summary': '2026-10-26', 'rating-gift-trend': '2026-10-26', 'bunding-sale-summary': '2026-10-26', 'bunding-sale-trend': '2026-10-26', 'content-realtime-summary': '2026-10-28', 'content-realtime-hourly': '2026-10-28', 'content-realtime-sku': '2026-10-28', 'brand-card-member-overall-shop-new': '2026-10-27', 'brand-card-member-overall-card-new': '2026-10-27', 'brand-card-member-overall-tier-top10': '2026-10-27', 'brand-card-member-shop-shop-new': '2026-10-27', 'brand-card-member-shop-card-new': '2026-10-27', 'brand-card-shop-shop-new': '2026-10-27', 'brand-card-shop-card-new': '2026-10-27', 'brand-card-shop-tier-top10': '2026-10-27', 'rating-gift-activities': '2026-10-27', 'bunding-sale-products': '2026-10-27', 'compete-overview-summary': '2026-10-26', 'compete-overview-shops': '2026-10-26', 'compete-overview-products': '2026-10-26', 'compete-overview-sources': '2026-10-26', 'compete-overview-keywords': '2026-10-26', 'compete-loss-summary': '2026-10-26', 'compete-loss-trend': '2026-10-26', 'compete-loss-shops': '2026-10-26', 'compete-loss-products': '2026-10-26', 'content-detail-article-summary': '2026-10-26', 'content-detail-article-trend': '2026-10-26', 'content-detail-article-contents': '2026-10-26', 'content-detail-article-sources': '2026-10-26', 'content-detail-article-products': '2026-10-26', 'content-detail-video-summary': '2026-10-26', 'content-detail-video-trend': '2026-10-26', 'content-detail-video-contents': '2026-10-26', 'content-detail-video-sources': '2026-10-26', 'content-detail-video-products': '2026-10-26', 'content-detail-live-summary': '2026-10-26', 'content-detail-live-trend': '2026-10-26', 'content-detail-live-contents': '2026-10-26', 'content-detail-live-sources': '2026-10-26', 'content-detail-live-products': '2026-10-26', 'content-detail-subtypes': '2026-10-26', 'compete-realtime-summary': '2026-10-27', 'compete-realtime-trend': '2026-10-27', 'compete-realtime-shops': '2026-10-27', 'compete-realtime-products': '2026-10-27', 'compete-realtime-sources': '2026-10-27', 'compete-loss-product-list': '2026-10-26', 'compete-search-list': '2026-10-26', 'compete-shop-filters': '2026-10-26', 'compete-shop-dates': '2026-10-26', 'compete-compare-summary': '2026-10-27', 'compete-compare-trend': '2026-10-27', 'compete-compare-sku-trade': '2026-10-27', 'compete-compare-sku-flow': '2026-10-27', 'compete-compare-spu-trade': '2026-10-27', 'compete-compare-spu-flow': '2026-10-27', 'compete-compare-sources': '2026-10-27', 'compete-product-spu-options': '2026-10-27', 'compete-product-spu-summary': '2026-10-27', 'compete-product-spu-trend': '2026-10-27', 'compete-product-sku-options': '2026-10-27', 'compete-product-sku-summary': '2026-10-27', 'compete-product-sku-trend': '2026-10-27', 'compete-product-sku-core-all': '2026-10-27', 'compete-product-sku-sources': '2026-10-27', 'compete-product-sku-keywords-flow': '2026-10-27', 'compete-product-sku-keywords-deal': '2026-10-27', 'compete-product-sku-customers': '2026-10-27', 'compete-product-spu-core-all': '2026-10-27', 'compete-product-spu-sources': '2026-10-27', 'compete-product-spu-keywords-flow': '2026-10-27', 'compete-product-spu-keywords-deal': '2026-10-27', 'compete-product-spu-customers': '2026-10-27', 'compete-monitor-product-count': '2026-10-27', 'compete-monitor-shop-count': '2026-10-27', 'compete-monitor-filters': '2026-10-27', 'compete-monitor-sku-products': '2026-10-27', 'compete-monitor-sku-trend': '2026-10-27', 'compete-monitor-sku-loss': '2026-10-27', 'compete-monitor-shop-sku-top': '2026-10-27', 'compete-monitor-spu-products': '2026-10-27', 'compete-monitor-spu-trend': '2026-10-27', 'compete-monitor-spu-loss': '2026-10-27', 'compete-monitor-shop-spu-top': '2026-10-27', 'compete-monitor-shops': '2026-10-27', 'compete-monitor-shop-trend': '2026-10-27', 'compete-compare-sources-level2': '2026-10-27', 'compete-compare-sources-level3': '2026-10-27', 'compete-product-sku-sources-level2': '2026-10-27', 'compete-product-sku-sources-level3': '2026-10-27', 'compete-product-spu-sources-level2': '2026-10-27', 'compete-product-spu-sources-level3': '2026-10-27', 'tool-single-filter-options': '2026-10-27', 'tool-total-filter-options': '2026-10-27', 'gift-money-detail-info': '2026-10-27', 'gift-money-detail-overview': '2026-10-27', 'gift-money-detail-daily': '2026-10-27', 'gift-money-detail-trend': '2026-10-27', 'gift-money-detail-products': '2026-10-27', 'compete-config-products': '2026-10-27', 'compete-config-shops': '2026-10-27', 'compete-realtime-config-shops': '2026-10-27'}

LIVE_VERIFIED_CHANNELS={'compete-compare-sku-flow': ['all'], 'compete-compare-sku-trade': ['all'], 'compete-compare-spu-flow': ['all'], 'compete-compare-spu-trade': ['all'], 'compete-compare-summary': ['all', 'app'], 'compete-compare-trend': ['all'], 'compete-monitor-shop-sku-top': ['all'], 'compete-monitor-shop-spu-top': ['all'], 'compete-monitor-shop-trend': ['all'], 'compete-monitor-shops': ['all', 'app'], 'compete-monitor-sku-loss': ['all'], 'compete-monitor-sku-products': ['all', 'app'], 'compete-monitor-sku-trend': ['all'], 'compete-monitor-spu-loss': ['all'], 'compete-monitor-spu-products': ['all', 'app'], 'compete-monitor-spu-trend': ['all'], 'compete-product-sku-core-all': ['all'], 'compete-product-sku-customers': ['all'], 'compete-product-sku-summary': ['all', 'app'], 'compete-product-sku-trend': ['all'], 'compete-product-spu-core-all': ['all'], 'compete-product-spu-customers': ['all'], 'compete-product-spu-summary': ['all', 'app'], 'compete-product-spu-trend': ['all']}

LIVE_VERIFIED_COMPETITION_CATEGORIES={'compete-compare-summary': ['男装', '女装', '童装'], 'compete-compare-trend': ['男装', '女装', '童装'], 'compete-compare-sku-trade': ['男装', '女装', '童装'], 'compete-compare-sku-flow': ['男装', '女装', '童装'], 'compete-compare-spu-trade': ['男装', '女装', '童装'], 'compete-compare-spu-flow': ['男装', '女装', '童装'], 'compete-compare-sources': ['男装', '女装', '童装'], 'compete-compare-sources-level2': ['男装', '女装', '童装'], 'compete-compare-sources-level3': ['男装', '女装', '童装'], 'compete-monitor-sku-products': ['男装', '女装', '童装'], 'compete-monitor-shop-sku-top': ['男装', '女装', '童装'], 'compete-monitor-spu-products': ['男装', '女装', '童装'], 'compete-monitor-shop-spu-top': ['男装', '女装', '童装'], 'compete-monitor-shops': ['男装', '女装', '童装'], 'compete-monitor-shop-trend': ['男装', '女装', '童装'], 'compete-monitor-spu-loss': ['男装', '女装', '童装'], 'compete-monitor-spu-trend': ['女装', '童装', '男装']}

def catalog():
    def row(name,reports=(),reused=(),pending=()):
        return {'module':name,'reports':list(reports),'reused_commands':list(reused),
                'status':'partial_verified' if any(k in LIVE_VERIFIED_20261027 for k in reports) else 'code_complete_pending_live' if reports else 'partial_reuse' if reused else 'pending_contract',
                'report_validation':{k:{'status':'live_verified' if k in LIVE_VERIFIED_20261027 else 'code_complete_pending_live',
                    'verified_date':LIVE_VERIFIED_DATES.get(k),'min_extension':CONTRACTS[k]['min_extension'],
                    'channel_options':CONTRACTS[k].get('channel_options',[]),'live_verified_channels':LIVE_VERIFIED_CHANNELS.get(k,[]),'competition_category_supported':bool(CONTRACTS[k].get('competition_category_options')),'live_verified_categories':LIVE_VERIFIED_COMPETITION_CATEGORIES.get(k,[])} for k in reports},
                'remaining':list(pending)}
    return {'platform':'jd','min_extension':'0.9.40','contract_count':len(CONTRACTS),
        'live_verified_contracts':len(LIVE_VERIFIED_20261027),'whole_scope_complete':False,
        'acceptance_record':'docs/jd-marketing-market-live-acceptance-2026-10-27.json',
        'competition_category_acceptance_record':'docs/jd-competition-category-acceptance-2026-10-28.json',
        'configuration_acceptance_record':'docs/jd-competition-configuration-acceptance-2026-10-28.json',
        'scope':'指定营销与市场模块的只读统计，不配置、关注、创建或推送',
        'modules':[
          row('促销工具分析',[k for k in CONTRACTS if k.startswith(('marketing-','tool-','cross-sell-','coupon-share-','shop-gift-','gift-money-','expansion-money-','brand-card-','rating-gift-','bunding-sale-'))],pending=['概览、趋势及品牌卡8项分组统计已验；评价有礼活动表为官方空结果，活动商品弹窗缺少有效活动样本；裂变券/礼包仅核验空结果；礼金--all-pages已核验32页314个唯一活动（当前列表，非单日业绩）；搭售商品达到1000行上限，不称全量，click_level/expo_level不推算；单品促销列表1000行及其他活动下钻/非默认筛选仍有限定范围；0.9.38礼金详情5项及单品/店铺筛选字典2项已验，礼金商品默认10/1216条非全量；所选活动请求日全部缺失/趋势为空不再反复尝试；个人卡号及交易流水不在聚合统计范围']),
          row('百亿补贴',[k for k in CONTRACTS if k.startswith('subsidy-')],pending=['汇总返回全空指标，商品明细返回空表；趋势30日期部分仅有日期字段，size=13不代表应有行数；不补零，不称全量']),
          row('内容营销分析',[k for k in CONTRACTS if k.startswith('content-')],pending=['图文/视频/直播历史明细16项已验，内容榜及部分商品表1000行不称全量；实时直播概览与小时查询已实测；SKU已按1000行上限实测返回178个唯一SKU；累计图复用小时查询；数字人原生页仅展示产品介绍，不当零数据或已接入']),
          row('行业动态',[k for k in CONTRACTS if k.startswith('industry-sellers-')],reused=['industry-options','industry-overview','industry-products','industry-shops'],pending=['行业卖家4项已按官方女装、男装、童装类目在线核验；其他类目尚未逐项实测；不重复接入已有大盘和榜单']),
          row('行业用户动态',[k for k in CONTRACTS if k.startswith('industry-buyers-')],pending=['类目字典及5项买家统计已按官方女装、男装、童装在线核验；支持精确二三级类目，非默认人群筛选未开放']),
          row('竞争分析',[k for k in CONTRACTS if k.startswith('compete-')],pending=['概况5项、店铺流失4项已验；实时5项、商品流失/搜索列表2项和对比字典2项已验；对比dates兼容命令实际返回页面开关，不含业务日期边界；新版竞店对比7项已实测（含官方7天趋势、SKU/SPU热销/人气榜、APP一级来源）；竞品SKU/SPU字典、概览/30天趋势6项已验；完整核心指标/APP一级来源/关键词两排序/画像及竞争概况元数据13项已验；画像仅验size=-1的官方小人群抑制结构；竞争概况商品/店铺列表、7天趋势、流失下钻及店铺SKU/SPU榜10项已验；流失仅验空结构，SKU趋势为空，SPU趋势缺失两项流失指标；店铺size=30实际31行（含本店）不当行总数；支持精确指定已监控目标和对比商品；APP站内场域二级及首页三级来源共6项已验；6类概览/监控表的APP筛选已验，其他渠道/对象/周期组合不称穷尽；非首页三级来源、非空画像/流失结构仍待样本；区间值原样保留；竞店对比/竞争概况男装女装童装51个类目组合已验，另6个SKU下钻无类目内有效样本，不再尝试；竞争配置9竞品/30竞店与实时配置30竞店只读信息已验；其余当前页面无原生类目参数的子模块不伪造筛选；配置写接口不接入'])]}


def verify_proof(proof, report, values, day, store, response_text):
    from ...core.stores import verify_identity
    validate(report,values,day,archive=True)
    if proof.get('case')!='business-stats' or proof.get('date')!=day or proof.get('business_report')!=report or proof.get('request_params')!=values or proof.get('source')!='registered-api':
        raise ValueError('统计证据请求范围不符。')
    if CONTRACTS[report]['method']=='POST' and proof.get('request_body')!=values:raise ValueError('统计POST原始请求体不符。')
    verify_identity({'platform':'jd','store_key':store},proof.get('identity'))
    if report.startswith('compete-compare-') and values['selfShopId']!=[store.removeprefix('jd:mall:')]:raise ValueError('竞店对比本店参数与证据店铺不符。')
    if not isinstance(response_text,str) or hashlib.sha256(response_text.encode()).hexdigest()!=proof.get('response_sha256'):
        raise ValueError('统计原始响应哈希不符。')
    start=datetime.fromisoformat(proof['request_started_at'].replace('Z','+00:00'))
    issued=datetime.fromisoformat(proof['dispatched_at'].replace('Z','+00:00'))
    if start.tzinfo is None or issued.tzinfo is None:raise ValueError('统计证据时间缺少时区。')
    if CONTRACTS[report]['scope']=='current_realtime' and any(t.astimezone(timezone(timedelta(hours=8))).date().isoformat()!=day for t in (issued,start)):raise ValueError('实时竞争快照的采集日期与归档日期不符。')
    if not 0<=(start-issued).total_seconds()<=60:
        raise ValueError('统计证据时间不符。')


def main(argv):
    from shopdate_workflows.evidence import read_evidence,write_evidence,save_json
    parser=argparse.ArgumentParser(description='京东营销与市场固定只读统计；已有行业接口复用，写配置不接入。',allow_abbrev=False)
    parser.add_argument('command',choices=['business-modules','business-analysis'])
    parser.add_argument('--report',choices=sorted(CONTRACTS))
    parser.add_argument('--date',help='历史统计完整历史日；实时竞争仅北京时间今日，历史快照须用evidence重放');parser.add_argument('--store');parser.add_argument('--evidence')
    parser.add_argument('--category',help='仅行业买家/卖家：官方精确二/三级名称或ID；省略取官方主类目')
    parser.add_argument('--compare-shop',help='仅新版竞店对比：已配置竞店精确名称或ID；省略取官方字典首个竞店并标明选择')
    parser.add_argument('--all-pages',action='store_true',help='仅礼金活动：读完官方全部页并复查首页与活动ID数量')
    parser.add_argument('--target-id','--activity-id',dest='target_id',help='官方已监控商品/竞店或礼金活动ID；省略取本次官方列表首项，礼金仅本次返回页')
    parser.add_argument('--self-product-id',help='竞品对比本品ID，必须在官方本品字典内')
    parser.add_argument('--compare-product-id',help='竞品对比竞品ID，必须在官方已监控竞品字典内')
    parser.add_argument('--channel',choices=['all','app'],help='仅登记的现代竞品/竞店/监控查询支持all或app；来源下钻固定APP')
    args=parser.parse_args(argv)
    try:
        if args.store is not None and not re.fullmatch(r'jd:mall:\d+',args.store):
            raise ValueError('必须用精确京东store_key。')
        if args.command=='business-modules':
            if args.report or args.date or args.evidence or args.category or args.compare_shop or args.all_pages or args.target_id or args.self_product_id or args.compare_product_id or args.channel:raise ValueError('目录不接受取数参数。')
            print(json.dumps(catalog(),ensure_ascii=False));return 0
        if not args.report or not args.date or not args.store:raise ValueError('请指定report、date和store。')
        needs_category='$SECOND_ID' in CONTRACTS[args.report]['template'].values()
        needs_shops=args.report.startswith('compete-compare-')
        needs_products=CONTRACTS[args.report].get('requires_products',False)
        needs_target=bool(CONTRACTS[args.report].get('target_kind'))
        competition_options=CONTRACTS[args.report].get('competition_category_options')
        if args.category and (not (needs_category or competition_options) or args.evidence):raise ValueError('该报告未登记类目视角，或证据重放不能更改筛选。')
        if args.compare_shop and (not needs_shops or args.evidence):raise ValueError('竞店选择只用于新版对比，证据重放不能更改筛选。')
        if args.all_pages and (args.report!='gift-money-activities' or args.evidence):raise ValueError('全量分页仅用于礼金新采集，重放按原证据范围。')
        if args.target_id and (not needs_target or args.evidence):raise ValueError('对象ID仅用于登记的新下钻，重放不更改对象。')
        if (args.self_product_id or args.compare_product_id) and (not needs_products or args.evidence):raise ValueError('本品/竞品选择只用于竞品对比新采集，重放不更改选择。')
        if args.channel and (args.evidence or args.channel not in CONTRACTS[args.report].get('channel_options',[])):raise ValueError('渠道仅用于支持该选项的新采集；重放不改筛选。')
        product_query={'self_id':args.self_product_id,'compare_id':args.compare_product_id} if args.self_product_id or args.compare_product_id else None
        query_channel=args.channel
        values=None if needs_category or needs_shops or needs_products or needs_target else params(args.report,args.date,channel=query_channel,archive=bool(args.evidence))
        folder=ROOT/'data/business-stats'/args.store.replace(':','_')/args.date/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex[:8])
        requests=0
        if args.evidence:
            evidence=Path(args.evidence).resolve();payload=read_evidence(evidence,'jd',args.store)
            query_channel=payload['params'].get('channel') if CONTRACTS[args.report].get('channel_options') else None
            if not (needs_category or needs_shops or needs_products or needs_target):values=params(args.report,args.date,channel=query_channel,archive=True)
            if args.report in METRIC_CONTRACTS:values=validate(args.report,payload.get('params'),args.date,archive=True)
            if needs_category:
                cat=payload['category_evidence'];cat_params=params('industry-buyers-options',args.date)
                verify_proof(cat['proof'],'industry-buyers-options',cat_params,args.date,args.store,cat['response_text'])
                picked=choose_category(business_body(json.loads(cat['response_text'])),payload.get('category_query'))
                if picked!=payload.get('category_selection'):raise ValueError('类目字典选择证据不符。')
                values=params(args.report,args.date,category=picked['params'],channel=query_channel)
            if needs_shops:
                shop_evidence=payload['shop_evidence'];shop_params=params('compete-shop-options',args.date)
                verify_proof(shop_evidence['proof'],'compete-shop-options',shop_params,args.date,args.store,shop_evidence['response_text'])
                selected=choose_competitor(business_body(json.loads(shop_evidence['response_text'])),args.store,payload.get('compare_shop_query'))
                if selected!=payload.get('shop_selection'):raise ValueError('已配置竞店选择证据不符。')
                values=params(args.report,args.date,shops=selected['params'],channel=query_channel)
            if needs_products:
                unit=CONTRACTS[args.report]['product_unit'];option_report='compete-product-'+unit+'-options';option_params=params(option_report,args.date)
                product_evidence=payload['product_evidence']
                verify_proof(product_evidence['proof'],option_report,option_params,args.date,args.store,product_evidence['response_text'])
                selected_product=choose_products(business_body(json.loads(product_evidence['response_text'])),unit,args.store,payload.get('product_query'))
                if selected_product!=payload.get('product_selection'):raise ValueError('竞品选择与官方字典证据不符。')
                values=params(args.report,args.date,products=selected_product['params'],channel=query_channel)
            if needs_target:
                option_report=target_options(args.report);option_params=params(option_report,args.date);target_evidence=payload['target_evidence']
                verify_proof(target_evidence['proof'],option_report,option_params,args.date,args.store,target_evidence['response_text'])
                selected_target=choose_target(business_body(json.loads(target_evidence['response_text'])),args.report,args.store,payload.get('target_query'))
                if selected_target!=payload.get('target_selection'):raise ValueError('下钻对象与官方监控字典不符。')
                values=params(args.report,args.date,target=selected_target['target'],channel=query_channel)
            if payload.get('competition_category_evidence'):
                if not competition_options:raise ValueError('该报告不支持竞争类目证据。')
                ce=payload['competition_category_evidence'];cp=params(competition_options,args.date)
                verify_proof(ce['proof'],competition_options,cp,args.date,args.store,ce['response_text'])
                cs=choose_competition_category(business_body(json.loads(ce['response_text'])),payload.get('competition_category_query'))
                if cs!=payload.get('competition_category_selection'):raise ValueError('竞争类目选择与官方字典证据不符。')
                values={**values,**cs['params'],'monitorDim':'cate'}
                if CONTRACTS[args.report].get('target_kind')=='product':
                    unit=CONTRACTS[args.report]['product_unit'];table_report='compete-monitor-'+unit+'-products';ce_target=payload.get('category_target_evidence')
                    if not ce_target:raise ValueError('该类目下钻缺少对象属于所选类目的证据，不能当类目验收。')
                    tp=params(table_report,args.date,channel=query_channel,competition_category=cs['params'])
                    verify_proof(ce_target['proof'],table_report,tp,args.date,args.store,ce_target['response_text'])
                    normalized=normalize(json.loads(ce_target['response_text']),table_report,day=args.date,store=args.store,values=tp)
                    candidates=[r[unit+'_id'] for r in normalized['data']['data'] if r.get('type')=='detail']
                    if selected_target['target'] not in candidates:raise ValueError('下钻对象不在该类目官方监控结果中。')
            if (payload.get('command'),payload.get('report'),payload.get('date'),payload.get('params'))!=('business-analysis',args.report,args.date,values):raise ValueError('统计证据命令、日期或参数不符。')
        else:
            from .api_client import APIClient
            category_evidence=None;picked=None;shop_evidence=None;selected=None;pagination_evidence=None;product_evidence=None;selected_product=None;target_evidence=None;selected_target=None
            competition_category_evidence=None;competition_category_selection=None;category_target_evidence=None;target_query=args.target_id
            with APIClient({'platform':'jd','store_key':args.store},min_extension=CONTRACTS[args.report]['min_extension']) as client:
                try:
                    if needs_category:
                        cat_params=params('industry-buyers-options',args.date)
                        cat_raw,cat_proof=client.request('business-stats',args.date,scope={'report':'industry-buyers-options','params':cat_params});requests+=1
                        category_evidence={'response_text':client.last_response_text,'proof':cat_proof}
                        picked=choose_category(business_body(cat_raw),args.category)
                        values=params(args.report,args.date,category=picked['params'],channel=query_channel)
                    if needs_shops:
                        shop_params=params('compete-shop-options',args.date)
                        shop_raw,shop_proof=client.request('business-stats',args.date,scope={'report':'compete-shop-options','params':shop_params});requests+=1
                        shop_evidence={'response_text':client.last_response_text,'proof':shop_proof}
                        selected=choose_competitor(business_body(shop_raw),args.store,args.compare_shop)
                        values=params(args.report,args.date,shops=selected['params'],channel=query_channel)
                    if needs_products:
                        unit=CONTRACTS[args.report]['product_unit'];option_report='compete-product-'+unit+'-options';option_params=params(option_report,args.date)
                        product_raw,product_proof=client.request('business-stats',args.date,scope={'report':option_report,'params':option_params});requests+=1
                        product_evidence={'response_text':client.last_response_text,'proof':product_proof}
                        selected_product=choose_products(business_body(product_raw),unit,args.store,product_query)
                        values=params(args.report,args.date,products=selected_product['params'],channel=query_channel)
                    if needs_target:
                        option_report=target_options(args.report);option_params=params(option_report,args.date)
                        target_raw,target_proof=client.request('business-stats',args.date,scope={'report':option_report,'params':option_params});requests+=1
                        target_evidence={'response_text':client.last_response_text,'proof':target_proof}
                        selected_target=choose_target(business_body(target_raw),args.report,args.store,args.target_id)
                        values=params(args.report,args.date,target=selected_target['target'],channel=query_channel)
                    if args.category and competition_options:
                        cp=params(competition_options,args.date)
                        cr,proof_c=client.request('business-stats',args.date,scope={'report':competition_options,'params':cp});requests+=1
                        competition_category_evidence={'response_text':client.last_response_text,'proof':proof_c}
                        competition_category_selection=choose_competition_category(business_body(cr),args.category)
                        values={**values,**competition_category_selection['params'],'monitorDim':'cate'}
                        if CONTRACTS[args.report].get('target_kind')=='product':
                            unit=CONTRACTS[args.report]['product_unit'];table_report='compete-monitor-'+unit+'-products'
                            tp=params(table_report,args.date,channel=query_channel,competition_category=competition_category_selection['params'])
                            tr,tproof=client.request('business-stats',args.date,scope={'report':table_report,'params':tp});requests+=1
                            category_target_evidence={'response_text':client.last_response_text,'proof':tproof}
                            normalized=normalize(tr,table_report,day=args.date,store=args.store,values=tp)
                            candidates=[r[unit+'_id'] for r in normalized['data']['data'] if r.get('type')=='detail']
                            eligible={str(r['value']) for r in business_body(target_raw)['data'] if r.get('type')=='compare' and r.get('disabled') is False}
                            candidates=[v for v in candidates if v in eligible]
                            if not candidates:raise ValueError('所选类目暂无有数据的可用监控商品，未发送对象下钻查询。')
                            target_query=args.target_id or candidates[0]
                            if target_query not in candidates:raise ValueError('指定下钻对象不在所选类目官方监控结果中。')
                            selected_target=choose_target(business_body(target_raw),args.report,args.store,target_query)
                            values=params(args.report,args.date,target=selected_target['target'],channel=query_channel,competition_category=competition_category_selection['params'])
                    raw,proof=client.request('business-stats',args.date,scope={'report':args.report,'params':values});requests+=1
                    first_response_text=client.last_response_text
                    if args.all_pages:
                        from .business_paging import collect_remaining
                        pagination_evidence=collect_remaining(client,args.date,{'response_text':first_response_text,'proof':proof,'params':values},folder)
                        requests+=len(pagination_evidence)
                except (ValueError,KeyError,TypeError,OSError,RuntimeError) as exc:
                    failure={'platform':'jd','store_key':args.store,'date':args.date,'report':args.report,'status':'failed_not_accepted',
                        'params':values,'error':str(exc),'response_text':client.last_response_text,
                        'context':getattr(client,'last_response_context',None)}
                    save_json(folder/'failure.json',failure)
                    raise ValueError(str(exc)+'；失败原文已保存：'+str(folder/'failure.json')) from exc
            payload={'platform':'jd','store_key':args.store,'command':'business-analysis','date':args.date,
                     'report':args.report,'params':values,'response_text':first_response_text,'proof':proof,
                     'category_evidence':category_evidence,'category_selection':picked,'category_query':args.category,
                     'shop_evidence':shop_evidence,'shop_selection':selected,'compare_shop_query':args.compare_shop,
                     'product_evidence':product_evidence,'product_selection':selected_product,
                     'product_query':product_query,
                     'target_evidence':target_evidence,'target_selection':selected_target,'target_query':target_query,
                     'category_target_evidence':category_target_evidence,
                     'pagination_evidence':pagination_evidence,'all_pages':args.all_pages,
                     'competition_category_evidence':competition_category_evidence,'competition_category_selection':competition_category_selection,
                     'competition_category_query':args.category if competition_options else None}
            evidence=folder/'evidence.json';write_evidence(evidence,payload)
        verify_proof(payload['proof'],args.report,values,args.date,args.store,payload['response_text'])
        result=normalize(json.loads(payload['response_text']),args.report,day=args.date,store=args.store,values=values)
        if payload.get('all_pages'):
            if args.report!='gift-money-activities':raise ValueError('未登记的全量分页证据。')
            from .business_paging import verify_saved
            result=verify_saved(payload,args.date,args.store)
        report={'platform':'jd','store_key':args.store,'date':args.date,'command':'business-analysis','report':args.report,
                'status':'partial','query_status':'ok','scope':CONTRACTS[args.report]['scope'],
                'collection_mode':'replay' if args.evidence else 'live','source_requests_this_call':requests,
                'params':values,'result':result,'evidence_path':str(evidence)}
        if needs_category:report['category_selection']=payload['category_selection']
        if needs_shops:report['shop_selection']=payload['shop_selection']
        if needs_products:report['product_selection']=payload['product_selection']
        if needs_target:report['target_selection']=payload['target_selection']
        if payload.get('competition_category_selection'):report['competition_category_selection']=payload['competition_category_selection']
        if payload.get('category_target_evidence'):report['category_target_membership_verified']=True
        save_json(folder/'report.json',report)
        print(json.dumps({**report,'report_path':str(folder/'report.json')},ensure_ascii=False));return 0
    except (ValueError,KeyError,TypeError,OSError,RuntimeError) as exc:
        print(str(exc),file=sys.stderr);return 1
