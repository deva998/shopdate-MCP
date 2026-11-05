"""Fixed read-only SYCM marketing/trade queries observed via MCP, 2026-11-04.

Existing product/sales/refund list commands are deliberately reused, not copied.
Public sources: op-sales 1.0.95; op-live 5.0.90; op-fa 1.0.36.
"""
import json
import re
import time
import calendar
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import urlsplit


@contextmanager
def trace_bridge(server, records):
 original=server.submit
 def submit(job,timeout):
  begin=time.monotonic()
  entry={'kind':'cookie' if job.get('cookie') else 'request','path':urlsplit(job.get('url','')).path,'timeout_seconds':timeout}
  records.append(entry)
  try:
   result=original(job,timeout)
   entry.update(status=result.get('status'),text_length=len(result.get('text') or ''),returned_error=bool(result.get('error')))
   timing=result.get('_pageTiming') or {}
   if isinstance(timing.get('startedAt'),(int,float)) and isinstance(timing.get('finishedAt'),(int,float)):
    entry['page_elapsed_ms']=timing['finishedAt']-timing['startedAt']
   return result
  except Exception as error:
   entry['error_type']=type(error).__name__;raise
  finally:entry['elapsed_ms']=round((time.monotonic()-begin)*1000,2)
 server.submit=submit
 try:yield
 finally:server.submit=original

TOOLS={
 'commonItemPromotion':('单品宝','payItmCnt,payByrCnt,payAmt,payUnitPrice'),
 'shopPromotion':('店铺宝','payMordCnt,payByrCnt,payAmt,avgPayCnt,payUnitPrice,payItmCnt'),
 'collocationId':('搭配宝','payMordCnt,payByrCnt,payAmt,cartOrderRate,payItmCnt,payOrdCnt,payUnitPrice,avgPayCnt'),
 'quotaPick':('N元任选','payMordCnt,payByrCnt,payAmt,avgPayCnt,payUnitPrice,payItmCnt'),
 'shopbonus':('店铺券','getCouponsCnt,useCouponsCnt,payAmt,payByrCnt,payItmCnt,payUnitPrice'),
 'itemcoupon':('商品券','getCouponsCnt,useCouponsCnt,payAmt,payByrCnt,payItmCnt,payUnitPrice'),
 'spsd4kefu':('客服专属优惠','couponSendCnt,couponSendAmt,payOrdCnt,payOrdAmt,payOrdByrCnt,couponsUseRate'),
 'spsd4htklj':('回头客立减','discountPayAmt,payItmCnt,payAmt,payByrCnt'),
 'spsd4price':('单品立减','discountPayAmt,payItmCnt,payAmt,payByrCnt'),
}
METHODS={'newer':'新客折扣','older':'新客礼金','gouwujin':'购物金','maifan':'买返购物金'}
METHOD_METRICS={
 'newer':'guideNewUv,guideNewPayByrCnt,guideNewPayByrCntRatio,guideNewPayAmt,guideNewPayAmtRatio,guideNewPayRate,shopNewbuyerPayRate',
 'older':'newItemGuideUv,newItemGuidePayByrCnt,newItemGuidePayByrCntRatio,newItemGuidePayAmt,newItemGuidePayAmtRatio,newItemGuidePayRate',
 'gouwujin':'verAmt,verOrdCnt,repByrCnt,repAmt,repOrdCnt',
 'maifan':'sendAmt,sendByrCnt,sendOrdCnt,verAmt,verByrCnt,verOrdCnt,payOrdAmt',
}
REPORTS={
 'video-overview':'商品视频全店整体概览（不是商品列表求和）',
 'video-trend':'商品视频整体近30日趋势（官方日期轴）',
 'sales-benchmark-categories':'销售趋势同行对比类目字典（不是店内类目筛选）',
 'marketing-method-skus':'购物金商品SKU下钻',
 'marketing-activity-grade-config':'店铺宝活动阶梯只读定义',
 'marketing-activity-grades':'店铺宝活动分级效果',
 'refund-live-overview':'交易退款实时汇总（今日/昨日）',
 'refund-live-trend':'交易退款实时趋势（官方小时轴）',
 'refund-close-overview':'交易已完结退款历史汇总',
 'refund-close-trend':'复用历史退款汇总逐日形成的支付日期序列（非独立趋势接口）',
 'refund-reasons':'交易退款洞察原因树（不替代退款汇总）',
 'sales-category-leaf':'销售分析叶子类目构成',
 'marketing-tool-overview':'营销工具效果总览',
 'marketing-tool-trend':'营销工具趋势',
 'marketing-tool-activities':'营销工具活动列表',
 'marketing-activity-overview':'营销活动分日概览',
 'marketing-activity-trend':'营销活动分日趋势',
 'marketing-activity-items':'营销活动商品榜',
 'marketing-method-overview':'营销玩法概览',
 'marketing-method-trend':'营销玩法趋势',
 'marketing-method-items':'营销玩法商品榜',
 'marketing-method-item-trend':'营销玩法单品趋势',
 'realtime-overview':'实时概况快照',
 'realtime-trend':'实时概况趋势',
 'realtime-ranking':'实时商品排行',
 'realtime-cart-ranking':'实时加购商品排行',
 'realtime-sources':'实时来源树',
 'realtime-areas':'实时地域分布',
 'realtime-yesterday-flow':'昨日实时流量对照',
 'realtime-yesterday-trade':'昨日实时交易对照',
 'realtime-industry-rank':'实时行业排名',
 'sales-detail':'销售分析原生销售明细',
 'sales-overview':'销售分析交易概览',
 'sales-trend':'销售分析以截止日为准的近30日趋势',
 'sales-device-structure':'销售分析终端构成',
 'sales-category-structure':'销售分析一级类目构成',
 'sales-price-structure':'销售分析价格带构成',
 'sales-brand-structure':'销售分析品牌构成',
}
EXCLUDED={
 '实时推广':'用户明确排除',
 '实时访客':'官方 op-live 5.0.90 路由注明2024-08-29下线，不恢复旧接口',
 '营销托管':'官方跳转 ppxk 外部系统，当前 MCP 无该系统数据接口',
 '智能优惠':'官方内嵌千牛页面，尚缺对应只读统计契约',
}


def supported_periods(report,method='newer'):
 if report=='video-overview':return ['day']
 if report=='video-trend':return ['day','recent30']
 if report.startswith(('realtime-','refund-live-')):return []
 if report=='marketing-activity-grade-config':return []
 if report.startswith('refund-'):return ['day','recent7','recent30','week','month','range']
 if report=='sales-detail' or report.startswith('marketing-activity-'):return ['day']
 if report in ('sales-trend','sales-benchmark-categories'):return ['day','recent30','week','month']
 if report.startswith('sales-'):return ['day','recent7','recent30','week','month']
 if report.startswith('marketing-tool-'):return ['day','recent7','recent30']
 if report.startswith('marketing-method-'):
  if report=='marketing-method-skus' and method!='gouwujin':return []
  if report=='marketing-method-item-trend' and method not in ('newer','older'):return []
  return ['day','week','month'] if method in ('newer','older') else ['day','recent7','recent30','compareRange']
 return []


def historical_period(report,method,start,end,today,period,compare_start,compare_end):
 first=date.fromisoformat(start) if start else today-timedelta(days=1)
 last=date.fromisoformat(end) if end else first
 days=(last-first).days+1
 if last>=today or days<1:raise ValueError('日期需为已结束的历史区间，起日不能晚于止日')
 if period is None:
  if compare_start or compare_end:raise ValueError('对比日期必须显式指定period=compareRange')
  if days not in (1,7,30):raise ValueError('默认仅支持完整历史日及原生7/30天窗口；其他周期请显式指定period')
  return first,last,{'dateType':{1:'day',7:'recent7',30:'recent30'}[days],'dateRange':f'{first}|{last}'}
 if period not in supported_periods(report,method):raise ValueError('所选报表没有该周期的官方声明，不能用其他周期代替')
 if period in ('week','month','range','compareRange') and (not start or not end):raise ValueError('周、月和自定义区间需显式提供起止日期')
 if period=='week' and (first.weekday()!=0 or days!=7):raise ValueError('自然周必须为完整周一至周日')
 if period=='month' and (first.day!=1 or first.year!=last.year or first.month!=last.month or last.day!=calendar.monthrange(first.year,first.month)[1]):raise ValueError('自然月必须为同月第一日至最后一日')
 if period in ('day','recent7','recent30') and days!={'day':1,'recent7':7,'recent30':30}[period]:raise ValueError('周期天数与dateType不一致')
 if period in ('range','compareRange') and days>31:raise ValueError('自定义区间最长31天')
 params={'dateType':period,'dateRange':f'{first}|{last}'}
 if period=='compareRange':
  if not compare_start or not compare_end:raise ValueError('自定义对比必须提供当前区间和对比区间')
  cf,cl=date.fromisoformat(compare_start),date.fromisoformat(compare_end)
  if not 1<=(cl-cf).days+1<=31 or cl>=today:raise ValueError('对比区间需为已结束的1至31天')
  params['dateRange']+=f',{cf}|{cl}'
 elif compare_start or compare_end:raise ValueError('该周期不接受对比日期')
 return first,last,params


def build_request(report, *, start=None, end=None, today=None, tool='commonItemPromotion',
                  method='newer', device=None, index=None, page=1, limit=10,
                  activity_id=None, item_id=None, act_status='1',act_type=None,act_range=None,keyword=None,category_id=None,refund_date_type='pay',period=None,compare_start=None,compare_end=None,compare_category_id=None,benchmark=None,sort_by=None,sort_order=None):
 if report not in REPORTS:raise ValueError('未知或排除的只读报表')
 if report.startswith('video-') and index is not None:raise ValueError('视频汇总返回官方完整指标，不接受未声明的index筛选')
 today=today or datetime.now(timezone(timedelta(hours=8))).date()
 if tool not in TOOLS or method not in METHODS:raise ValueError('未知官方工具或玩法')
 if act_type is not None and (report!='marketing-tool-activities' or tool!='collocationId' or act_type not in ('1','2')):raise ValueError('act-type只适用于搭配宝活动列表')
 if act_range is not None and (report!='marketing-tool-activities' or tool!='shopPromotion' or act_range not in ('shopPromotionAll','shopPromotionPart')):raise ValueError('act-range只适用于店铺宝活动列表')
 if keyword is not None and (report!='marketing-tool-activities' or tool=='spsd4kefu' or len(keyword)>100):raise ValueError('keyword仅用于已核对的原生活动列表，最多100字符')
 if category_id is not None and report!='sales-category-leaf':raise ValueError('category-id仅用于店内销售叶子类目；销售趋势的categoryId是同行对比类目，请用compare-category-id')
 if (compare_category_id is not None or benchmark is not None) and report!='sales-trend':raise ValueError('同行对比只适用于销售趋势')
 if device is not None and not (report.startswith('realtime-') or (report.startswith('sales-') and report not in ('sales-detail','sales-benchmark-categories'))):raise ValueError('该报表未声明终端筛选，不静默忽略device')
 if sort_by is not None or sort_order is not None:
  if report!='marketing-method-items' or method!='gouwujin' or sort_by not in (None,'rcAmt','itmUv','rcByrCnt','rcCapitalAmt','rcRate','avgRcAmt','rechargeOrdCnt','rechargeItemCnt','rechargeSucRfdAmt') or sort_order not in (None,'asc','desc'):raise ValueError('仅支持购物金商品表官方声明指标排序')
 device=device or ('2' if report=='realtime-sources' else '0')
 if device not in ('0','1','2'):raise ValueError('device 必须为0/1/2')
 if report=='realtime-sources' and device=='0':raise ValueError('官方实时来源只接受device=1或2；默认无线端2，不合成全端')
 if isinstance(page,bool) or not isinstance(page,int) or page<1 or isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=100:raise ValueError('分页需 page>=1，limit为1至100')
 p={};scope='requested_historical_window'
 if report.startswith(('realtime-','refund-live-')) and (period or compare_start or compare_end):raise ValueError('实时查询不接受历史周期或对比区间')
 if report.startswith('refund-live-'):
  if start or end:raise ValueError('退款实时接口只支持今日，不接受历史日期')
  return '/csp/api/refund/live/'+('overview.json' if report.endswith('overview') else 'trend.json'),{'dateType':'today'},'current_snapshot_with_yesterday_comparison'
 if report.startswith('realtime-'):
  if start or end:raise ValueError('实时查询不接受历史日期，返回当前快照或官方昨日对照')
  scope='yesterday_comparison' if 'yesterday' in report else 'current_snapshot'
  index=index or ('uv' if report=='realtime-areas' else 'cartItmCnt' if report=='realtime-cart-ranking' else 'payAmt')
  if index not in ('uv','pv','payAmt','buyerCnt','payRate','cartItmCnt'):raise ValueError('未知实时指标')
  paths={
   'realtime-overview':('/ipoll/live/getFlowAndPay.json',{'dtMaxAge':1000}),
   'realtime-trend':('/ipoll/live/summary/getTrend.json',{'device':device,'index':index}),
   'realtime-ranking':('/ipoll/live/rank/item.json',{'device':device,'index':index,'keyword':'','page':page,'limit':limit}),
   'realtime-cart-ranking':('/ipoll/live/rank/item/purchase/add.json',{'device':device,'index':index,'keyword':'','page':page,'limit':limit}),
   'realtime-sources':('/flow/v5/live/shop/source/tree/v3.json',{'device':device,'dateType':'today','dateRange':f'{today}|{today}','order':'desc','orderBy':'uv'}),
   'realtime-areas':('/ipoll/live/source/getAreaDistribution.json',{'device':device,'index':index,'dtUpdateTime':'false','dtMaxAge':5000}),
   'realtime-yesterday-flow':('/ipoll/live/yesterday/getYesterdayFlow.json',{}),
   'realtime-yesterday-trade':('/ipoll/live/yesterday/getYesterdayTrade.json',{}),
   'realtime-industry-rank':('/ipoll/live/summary/getIndustryRank.json',{'device':device}),
  }
  path,p=paths[report]
  return path,p,scope
 first,last,p=historical_period(report,method,start,end,today,period,compare_start,compare_end)
 if report.startswith('video-'):
  if p['dateType'] not in supported_periods(report):raise ValueError('该视频报表仅开放已核验的日期口径')
  p['belongType']='all'
  if report=='video-trend':
   p.update(dateType='recent30',dateRange=f'{last-timedelta(days=29)}|{last}')
   scope='native_trailing_30_days'
  return '/cc/video/'+('overview.json' if report=='video-overview' else 'trend.json'),p,scope
 if report in ('refund-close-overview','refund-close-trend'):
  if refund_date_type!='pay':raise ValueError('当前官方页面仅声明订单支付时间pay口径')
  p['refundDateType']=refund_date_type
  return '/csp/api/refund/close/overview.json',p,'daily_payment_cohort_series' if report=='refund-close-trend' else scope
 if report=='refund-reasons':
  p.update(rfdIdentifyType='alg_identify',refundDateType='pay',caseScene='ALL',rfdIntervalLevel='99',page=page,pageSize=limit,orderBy='shopSucRfdByr',order='desc')
  return '/csp/api/refund/reason/list/v2.json',p,scope
 if report=='sales-detail':
  p.update(page=page,pageSize=limit)
  return '/fa/trade/tradeDetail.json',p,scope
 if report.startswith('sales-'):
  paths={'sales-overview':'overview/get_summary.json','sales-trend':'overview/getTendency.json',
    'sales-device-structure':'constitute/getDeviceDetail.json','sales-category-structure':'constitute/listLevelOneCategory.json',
    'sales-price-structure':'constitute/getPriceDetail.json','sales-brand-structure':'constitute/listBrands.json','sales-category-leaf':'constitute/listLfCategory.json','sales-benchmark-categories':'overview/getCateTop.json'}
  p.update(device=device,dtUpdateTime='true')
  if report=='sales-trend':
   if index not in (None,'payAmt','payBuyerCnt','payPct','orderAmt','orderBuyerCnt','payRate','orderToPayRate'):raise ValueError('销售趋势指标没有官方声明')
   if (compare_category_id is None)!=(benchmark is None):raise ValueError('同行对比需同时指定字典类目ID及average/excellent')
   if compare_category_id is not None and (not re.fullmatch(r'[0-9]+',compare_category_id) or benchmark not in ('average','excellent')):raise ValueError('同行对比参数不合法')
   p.update(categoryId=compare_category_id or '',diff={'average':'1','excellent':'2'}.get(benchmark,'0'),indexs=index or 'payAmt')
   if period is None:
    p.update(dateType='recent30',dateRange=f'{last-timedelta(days=29)}|{last}')
    scope='native_trailing_30_days'
  if report=='sales-category-leaf':
   if not category_id or not re.fullmatch(r'[0-9]+',category_id):raise ValueError('叶子类目下钻需要官方父类目ID')
   p['categoryId']=category_id
  if report in ('sales-category-structure','sales-brand-structure','sales-category-leaf'):
   p.update(page=page,pageLimit=limit,orderField='payAmt',orderDirection='false')
  return '/bda/tradinganaly/'+paths[report],p,scope
 if report.startswith('marketing-tool-') or report.startswith('marketing-activity-'):
  p['toolId']=tool
  if report in ('marketing-activity-grade-config','marketing-activity-grades'):
   if tool!='shopPromotion' or not activity_id or not re.fullmatch(r'[0-9]+',activity_id):raise ValueError('阶梯下钻只适用于官方店铺宝活动ID')
   if report.endswith('config'):return '/xsite/sale/getSaleToolShopGrade.json',{'actId':activity_id,'dtUpdateTime':'true'},'activity_metadata'
   p.update(actId=activity_id,page=page,pageSize=limit)
   return '/xsite/sale/getSaleToolActGradeOverall.json',p,scope
  prefix='/cc/sale/' if tool in ('spsd4htklj','spsd4price') else '/xsite/sale/'
  paths={'marketing-tool-overview':'getSaleToolSellerOverall.json','marketing-tool-trend':'getSaleToolSellerTrend.json',
   'marketing-tool-activities':'getSaleToolActList.json','marketing-activity-overview':'getSaleToolActOverall.json',
   'marketing-activity-trend':'getSaleToolActTrend.json','marketing-activity-items':'getSaleToolItemList.json'}
  path=prefix+paths[report]
  if prefix=='/cc/sale/' and report=='marketing-activity-overview':path=prefix+'getSaleToolActList.json'
  if report.startswith('marketing-activity-'):
   if not activity_id or not re.fullmatch(r'[0-9]+',activity_id):raise ValueError('活动下钻需要从官方列表取得的数字活动ID')
   p['actId']=activity_id
   if report=='marketing-activity-items' and tool not in ('commonItemPromotion','spsd4htklj','spsd4price'):raise ValueError('该工具的活动下钻为搭配/阶梯专用模块，不能套用单品商品榜')
   if prefix=='/cc/sale/' and report=='marketing-activity-items':path=prefix+'getSaleTool/detail.json';p.update(order='desc',orderBy='payAmt')
  if report=='marketing-tool-activities':
   if act_status not in ('0','1'):raise ValueError('活动状态为0或1')
   p.update(actStatus=act_status,actName='',page=page,pageSize=limit)
   if tool=='collocationId':p['actType']=act_type or '1'
   if tool=='shopPromotion':p['actRange']=act_range or 'shopPromotionAll'
   if keyword:
    p['actId' if keyword.isdigit() else 'actName']=keyword
  if report=='marketing-activity-items':p.update(page=page,pageSize=limit)
  if 'trend' in report:
   index=index or ('payAmt' if 'payAmt' in TOOLS[tool][1].split(',') else 'payOrdAmt')
   if index not in TOOLS[tool][1].split(','):raise ValueError('指标不属于所选工具')
   p['indexCode']=index
  if tool=='spsd4kefu':
   if report not in ('marketing-tool-overview','marketing-tool-trend','marketing-tool-activities'):raise ValueError('客服专属优惠活动下钻契约待核实')
   ext={'toolId':tool,'sceneCode':'sycm'}
   code='tao.shop.shop.promotion'
   indexes=TOOLS[tool][1]
   if report=='marketing-tool-activities':
    ext={'toolId':tool,'actName':'','actStatus':act_status,'listAll':True}
    code+='.'+'customer.act';indexes='actId,sumCouponAmt,sumCouponsUseRate,couponsSendAmt,couponsUseRate'
   p.pop('toolId',None)
   p.update(bizCode='sycm_pc',domainCode=code,device='0',indexCodes=indexes,extMap=json.dumps(ext,separators=(',',':')))
   p['showType']='list' if report=='marketing-tool-activities' else 'trend' if 'trend' in report else 'overview'
   path='/domain/oneQuery.json'
  return path,p,scope
 if report.startswith('marketing-method-'):
  if report=='marketing-method-skus' and method!='gouwujin':raise ValueError('SKU下钻仅核对购物金')
  if method in ('newer','older'):
   p['channelId']={'newer':'450','older':'934'}[method]
   paths={'marketing-method-overview':'overview.json','marketing-method-trend':'trend.json',
          'marketing-method-items':'itemlist.json','marketing-method-item-trend':'itemlist/trend.json'}
   path='/s_content/brandnewdiscount/'+paths[report]
   if report=='marketing-method-items':
    p.update(page=page,pageSize=limit,order='desc',orderBy='newbuyerGuidePayByrCnt' if method=='newer' else 'newproductPayByrCnt')
   if report=='marketing-method-item-trend':
    if not item_id or not re.fullmatch(r'[0-9]+',item_id):raise ValueError('单品趋势需官方商品ID')
    p['itemId']=item_id
  else:
   if method=='gouwujin' and report in ('marketing-method-items','marketing-method-skus'):
    p.update(page=page,pageSize=limit)
    if report=='marketing-method-items':p.update(order=sort_order or 'desc',orderBy=sort_by or 'rcAmt')
    else:
     if not item_id or not re.fullmatch(r'[0-9]+',item_id):raise ValueError('SKU下钻需要官方购物金商品ID')
     p['itemId']=item_id
    name='ItemList.json' if report=='marketing-method-items' else 'ItemSkuList.json'
    return ('/cc/recharge/credit/activity/summary/get' if period=='compareRange' else '/xsite/rc/getRc')+name,p,scope
   if report not in ('marketing-method-overview','marketing-method-trend'):raise ValueError('购物金商品层下钻契约待核验')
   family='rc' if method=='gouwujin' else 'mf';stem='Rc' if family=='rc' else 'Mf'
   path=f'/xsite/{family}/get{stem}'+('Trend.json' if 'trend' in report else 'Overall.json')
   if period=='compareRange':
    if method=='gouwujin':path='/cc/recharge/credit/activity/summary/'+('getTrend.json' if 'trend' in report else 'getRcOverall.json')
    else:path='/xsite/mf/getMfCustom'+('Trend.json' if 'trend' in report else 'Overall.json')
  if 'trend' in report:
   index=index or METHOD_METRICS[method].split(',')[0]
   if index not in METHOD_METRICS[method].split(','):raise ValueError('指标不属于所选营销玩法')
   p['indexCode']=index
  return path,p,scope
 raise ValueError('未实现报表')


def summarize(response):
 if isinstance(response,dict) and 'hasError' in response:
  if response['hasError'] is not False or not isinstance(response.get('content'),dict):raise ValueError('官方营销查询返回错误封套')
  response=response['content']
 if not isinstance(response,dict) or isinstance(response.get('code'),bool) or response.get('code') not in (0,'0',200,'200'):raise ValueError('官方响应失败或缺少成功状态，不能解释为0')
 data=response.get('data');rows=None;total=None
 for _ in range(4):
  if not isinstance(data,dict) or 'code' not in data:break
  if isinstance(data['code'],bool) or data['code'] not in (0,'0',200,'200'):raise ValueError('官方内层响应失败，不能解释为0')
  data=data.get('data')
 # Real-time ranking uses a non-business wrapper {data:{reordCount,list},interval}.
 if isinstance(data,dict) and isinstance(data.get('data'),dict) and isinstance(data['data'].get('list'),list):data=data['data']
 if isinstance(data,list):rows=data
 elif isinstance(data,dict):
  for key in ('recordCount','total','totalCount'):
   if isinstance(data.get(key),int) and not isinstance(data[key],bool):total=data[key];break
  for key in ('data','records','rows','list'):
   if isinstance(data.get(key),list):rows=data[key];break
 empty=data is None or data=={} or data==[] or rows==[]
 result={'data_status':'no_data' if empty else 'ok','coverage':'returned_page_only' if rows is not None else 'official_response',
         'complete':False,'field_semantics':'official_raw_fields','notes':['首屏或返回树不证明全量；空数据不补零；来源访客与归因金额不可跨层求和。']}
 if rows is not None:result.update(row_count=len(rows),total=total)
 if isinstance(data,dict) and 'reordCount' in data:result['official_reordCount']=data['reordCount']
 if isinstance(data,dict) and isinstance(data.get('statDate'),list):
  axis=data['statDate'];result['coverage']='server_trend_window'
  result['returned_axis']=axis
  dates=[]
  for point in axis:
   if isinstance(point,(int,float)) and not isinstance(point,bool) and 0<=point<=4102444800000:
    dates.append(datetime.fromtimestamp(point/1000,timezone(timedelta(hours=8))).date().isoformat())
   elif isinstance(point,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',point):
    try:dates.append(date.fromisoformat(point).isoformat())
    except ValueError:dates.append(None)
   else:dates.append(None)
  result['returned_dates']=dates;result['date_axis_status']='ok' if dates and all(dates) else 'partial'
  mismatched=[k for k,v in data.items() if k!='statDate' and isinstance(v,list) and len(v)!=len(axis)]
  if mismatched or not dates or not all(dates) or len(set(dates))!=len(dates):
   result['data_status']='partial';result['date_axis_status']='partial';result['mismatched_series']=mismatched
  result['notes'].append('趋势使用官方返回时间轴，不将请求日期当作全部趋势点的日期。')
 return result


VIDEO_OVERVIEW_METRICS={
 'itemExposeUvNew':'曝光人数','singleEffectPlayUv':'播放人数','intentionByrCnt':'当日意向人数','daysDealUv':'当日成交人数',
 'singleEffectPlayPv':'播放次数','validPlayUv':'有效播放人数','contentValidPlayPv':'有效播放次数',
 'effectivePlayRate':'有效播放率','fullPlayeUv':'完整播放人数','vdoCompletePlayCnt':'完整播放次数',
 'completionRateNew':'完播率','playSecondsPerTimeNew':'次均播放时长',
}


def video_list_summary(data,params):
 """Page coverage only; never reconstruct shop UV or totals from product rows."""
 result=summarize({'code':0,'data':data})
 rows=data.get('data') or [];total=data.get('recordCount')
 ids=[(r.get('itemId') or {}).get('value') for r in rows]
 dates=[];sellers=[]
 for row in rows:
  stamp=(row.get('statDate') or {}).get('value')
  try:day=datetime.fromtimestamp(stamp/1000,timezone(timedelta(hours=8))).date().isoformat()
  except (ValueError,TypeError,OverflowError,OSError):day=None
  dates.append(day);sellers.append((row.get('sellerId') or {}).get('value'))
 page=int(params['page']);requested=int(params['pageSize'])
 valid_ids=all(v is not None for v in ids) and len(set(ids))==len(ids)
 expected=params.get('dateRange','').split('|');valid_dates=all(d and expected[0]<=d<=expected[-1] for d in dates)
 valid_sellers=all(s is not None for s in sellers) and len(set(sellers))<=1
 complete=page==1 and isinstance(total,int) and not isinstance(total,bool) and total==len(rows) and valid_ids and valid_dates and valid_sellers
 result.update(coverage='returned_product_page_only',complete=complete,actual_row_count=len(rows),unique_count=len(set(ids)),
  page=page,requested_page_size=requested,page_size_mismatch=len(rows)!=requested,
  returned_dates=sorted(set(d for d in dates if d)),seller_ids=sorted(set(s for s in sellers if s is not None)),
  notes=['此处为商品聚合列表，不是全店整体概览，也不是单条视频清单；全店使用business-query --report video-overview。',
         '使用实际返回条数，不能按请求pageSize推定覆盖；人数不能跨商品求和为全店去重人数。'])
 if not complete and result['data_status']=='ok':result['data_status']='partial'
 if not valid_ids or not valid_dates or not valid_sellers:result['data_status']='partial'
 return result


def report_summary(report,response,request_params=None):
 result=summarize(response)
 if report=='video-overview':
  data=response.get('data') or {}
  metrics={k:{'label':label,**(data.get(k) if isinstance(data.get(k),dict) else {'value':None})} for k,label in VIDEO_OVERVIEW_METRICS.items()}
  missing=[k for k,v in metrics.items() if not isinstance(v.get('value'),(int,float)) or isinstance(v.get('value'),bool)]
  stamp=(data.get('statDate') or {}).get('value')
  try:returned_date=datetime.fromtimestamp(stamp/1000,timezone(timedelta(hours=8))).date().isoformat()
  except (ValueError,TypeError,OverflowError,OSError):returned_date=None
  expected=(request_params or {}).get('dateRange','').split('|')
  identity_ok=(data.get('sellerId') or {}).get('value') is not None and (data.get('belongType') or {}).get('value')=='all'
  date_ok=returned_date is not None and len(expected)==2 and expected[0]==expected[1]==returned_date
  result.update(coverage='official_shop_video_overview',metrics=metrics,missing_metrics=missing,returned_date=returned_date,
   seller_id=(data.get('sellerId') or {}).get('value'),date_validation='ok' if date_ok else 'mismatch_or_missing',
   notes=['官方全店视频汇总原值，不由商品列表求和；播放人数与次数、完播人数与次数分别保留。','日期和素材来源按响应核验；未包含单条视频内容判断。'])
  if missing or not date_ok or not identity_ok:result['data_status']='partial'
 if report=='video-trend':
  if 'returned_dates' not in result:result['data_status']='partial'
  if request_params and result.get('returned_dates'):
   first,last=request_params['dateRange'].split('|')
   expected=[(date.fromisoformat(first)+timedelta(days=i)).isoformat() for i in range((date.fromisoformat(last)-date.fromisoformat(first)).days+1)]
   if result['returned_dates']!=expected:result['data_status']='partial';result['date_axis_status']='partial'
 if report=='realtime-sources':result['coverage']='returned_tree_only'
 if report=='sales-trend':
  data=response.get('data') or {}
  result['coverage']='unlabelled_native_series';result['date_axis_status']='not_returned';result['data_status']='partial'
  result['returned_last_day']=data.get('lastDay')
  result['series_shapes']=[{'device':row.get('device'),'point_counts':{k:len(v) for k,v in row.items() if isinstance(v,list)}} for row in data.get('self',[]) if isinstance(row,dict)]
  result['benchmark_series_shapes']=[{'device':row.get('device'),'point_counts':{k:len(v) for k,v in row.items() if isinstance(v,list)}} for row in data.get('diff',[]) if isinstance(row,dict)]
  result['notes']=['官方返回趋势数值及lastDay，但没有逐点日期轴，不自行把12个点标成所请求周/月内的日值。','categoryId/diff是同行类目基准，不筛选本店所属类目；self仍为所选终端的店铺趋势。']
  if request_params:
   try:
    anchor=date.fromisoformat(data['lastDay']);period=request_params['dateType']
    counts=[count for shape in result['series_shapes']+result['benchmark_series_shapes'] for count in shape['point_counts'].values()]
    if not counts or not 1<=max(counts)<=366 or len(set(counts))!=1:raise ValueError('趋势数组长度不一致')
    if request_params.get('diff','0')!='0' and not result['benchmark_series_shapes']:raise ValueError('没有返回同行数组')
    count=counts[0];axis=[]
    for offset in reversed(range(count)):
     if period=='month':
      serial=anchor.year*12+anchor.month-1-offset;year,month=divmod(serial,12);axis.append(f'{year:04}-{month+1:02}')
     elif period=='week':
      last=anchor-timedelta(weeks=offset);axis.append(f'{last-timedelta(days=6)}|{last}')
     else:axis.append((anchor-timedelta(days=offset)).isoformat())
    result.update(data_status='ok',coverage='native_series_with_client_derived_axis',date_axis_status='verified_official_client_rule',derived_period_axis=axis,
     axis_rule={'source_url':'https://g.alicdn.com/dt/ops-base/1.0.11/js/ops-base.js','sha256':'6e64122af55be61d6c92c8d589639b2fca11305bb09ede769e2a12bcb4cffcf7','component':'CommonChart.getLabels','origin':'official_client_rule_reconstruction_not_response_statDate'})
    result['notes'][0]='日期轴按已通过MCP读取的官方CommonChart.getLabels规则，由lastDay及实际点数重建；周为倒推7天区间，月为YYYY-MM，原始响应没有被添加或修改statDate。'
   except (ValueError,KeyError,TypeError):result['axis_rule_validation']='failed_or_missing_context'
 if not report.startswith('refund-'):return result
 data=response.get('data') or {}
 payload=data.get('data') if isinstance(data,dict) else None
 if report=='refund-close-overview':
  result['coverage']='returned_refund_scene_groups'
  result['notes']=['按订单支付时间归属的已完结退款，退款后续仍可能回补；不是当日实际退款发生额。空值保持缺失，不补零。']
  result['null_metrics']=[{'scene':row.get('caseScene'),'field':k} for row in payload or [] if isinstance(row,dict) for k,v in row.items() if isinstance(v,dict) and v.get('value') is None]
  if any(not isinstance(row.get('dateType'),dict) or row['dateType'].get('value')!='pay' for row in payload or [] if isinstance(row,dict)):
   result['data_status']='partial';result['notes'].append('响应未确认订单支付时间归属字段；保留请求pay及原始金额，不能宣称该日期口径已完整验证。')
  if request_params and request_params.get('refundDateType')=='pay':
   missing=[];conflicts=[]
   for row in payload or []:
    scene=(row.get('caseScene') or {}).get('value')
    fields=['shopSucRfdByr','shopSucRfdOrdCnt','ordRfdRate','shopRfdAmt','payAmtRfdRate']
    if scene=='THTK':fields.append('realPayrealRfdRate')
    for key in fields:
     value=(row.get(key) or {}).get('value')
     if not isinstance(value,(int,float)) or isinstance(value,bool):missing.append({'scene':scene,'field':key})
    basis=(row.get('dateType') or {}).get('value')
    if basis not in (None,'pay'):conflicts.append(scene)
   result.update(displayed_metric_missing=missing,basis_echo_status='not_returned' if any((r.get('dateType') or {}).get('value') is None for r in payload or []) else 'pay',
    basis_source='official_UI_request_contract',requested_refund_basis='pay',basis_conflicts=conflicts)
   if payload and not missing and not conflicts:
    result['data_status']='ok'
    result['notes']=['按官方页面SycmDomain请求契约refundDateType=pay解释；dateType是否回显另列，不伪造响应值。','只验官方页面展示的5项指标，退货退款场景另验realPayrealRfdRate；allSucRfdAmt等未展示字段缺失不阻断这组指标，原null保留。','支付日期归属退款会后续回补，不是退款发生日流水。']
 if report=='refund-live-trend':
  result['coverage']='official_hour_series';axes={};valid=True
  for group in ('today','yesterday'):
   row=payload.get(group,{}) if isinstance(payload,dict) else {}
   axis=row.get('statHour');axes[group]=axis
   valid=valid and isinstance(axis,list) and bool(axis) and len(axis)==len(set(axis)) and all(isinstance(x,str) and re.fullmatch(r'(?:[01][0-9]|2[0-3])',x) for x in axis)
   for metric in ('shopCloseRfdAmt','shopSucRfdAmt','shopAplRfdAmt'):
    values=row.get(metric)
    valid=valid and isinstance(values,list) and isinstance(axis,list) and len(values)==len(axis) and all(isinstance(v,(int,float)) and not isinstance(v,bool) for v in values)
  result.update(returned_hour_axes=axes,axis_status='ok' if valid else 'partial')
  result['notes']=['今日为实时未完结序列，昨日为官方对照；保留原始小时值，不自行加总、差分或补齐未来小时。']
  if not valid:result['data_status']='partial'
 return result


def page_data(response):
 summarize(response) # Reject failed envelopes before interpreting rows.
 data=response
 for _ in range(8):
  if not isinstance(data,dict):break
  if 'content' in data and 'hasError' in data:data=data['content'];continue
  if 'code' in data:data=data.get('data');continue
  break
 if isinstance(data,list):return data,None
 if isinstance(data,dict):
  total=next((data[k] for k in ('recordCount','total','totalCount') if isinstance(data.get(k),int) and not isinstance(data[k],bool) and data[k]>=0),None)
  rows=next((data[k] for k in ('data','records','rows','list') if isinstance(data.get(k),list)),None)
  return rows,total
 return None,None


def daily_refunds(fetch,first,last):
 records=[];failure=None;day=first
 while day<=last:
  try:
   raw=fetch(day);summary=report_summary('refund-close-overview',raw)
   records.append({'payment_date':day.isoformat(),'request':{'dateType':'day','dateRange':f'{day}|{day}','refundDateType':'pay'},'raw':raw,'summary':summary})
  except Exception as error:
   failure={'payment_date':day.isoformat(),'error_type':type(error).__name__};break
  day+=timedelta(days=1)
 status='partial' if failure or any(x['summary']['data_status']=='partial' for x in records) else 'no_data' if all(x['summary']['data_status']=='no_data' for x in records) else 'ok'
 return {'status':status,'raw_daily':records,'summary':{'data_status':status,'coverage':'daily_payment_cohort_series','complete':False,
  'requested_day_count':(last-first).days+1,'returned_day_count':len(records),'failure':failure,
  'series_origin':'derived_by_daily_calls_to_official_close_overview','notes':['逐日复用已完结退款汇总；按支付日期归属，后续退款会回补；非独立官方趋势接口。','各场景原值及缺失保留，不加总退款率，不以区间退款率代替逐日退款率。']}}


def pagination_options(report,options,all_pages):
 result=dict(options)
 if all_pages and report=='marketing-method-items' and options.get('method')=='gouwujin' and options.get('period')=='compareRange' and options.get('sort_by') is None and options.get('sort_order') is None:
  result.update(sort_by='itmUv',sort_order='asc')
 return result


def paginate(fetch,key,max_pages):
 if not 1<=max_pages<=200:raise ValueError('max-pages需为1至200')
 pages=[];seen=set();total=None;complete=False;reason='max_pages';failure=None
 for page in range(1,max_pages+1):
  try:raw=fetch(page)
  except Exception as error:
   if not pages:raise
   reason='request_failed';failure={'page':page,'error_type':type(error).__name__};break
  pages.append(raw)
  try:rows,current_total=page_data(raw)
  except ValueError as error:
   if len(pages)==1:raise
   reason='invalid_response';failure={'page':page,'error_type':type(error).__name__};break
  if current_total is None or rows is None:reason='missing_total';break
  if total is None:total=current_total
  if current_total!=total:reason='total_changed';break
  if not rows and total!=len(seen):reason='early_empty_page';break
  invalid=False
  for row in rows:
   value=row
   for part in key.split('.'):value=value.get(part) if isinstance(value,dict) else None
   if value is None or isinstance(value,(dict,list,bool)) or str(value)=='':reason='missing_entity_key';invalid=True;break
   value=str(value)
   if value in seen:reason='duplicate_entity';invalid=True;break
   seen.add(value)
  if invalid:break
  if len(seen)>total:reason='exceeds_total';break
  if len(seen)==total:complete=True;reason='official_total_reconciled';break
 verification=None
 if complete and len(pages)>1:
  try:verification=fetch(1);check_rows,check_total=page_data(verification)
  except Exception as error:
   complete=False;reason='verification_failed';failure={'page':1,'error_type':type(error).__name__};check_rows=None;check_total=None
  first_rows,_=page_data(pages[0])
  def keys(rows):
   values=[]
   for row in rows or []:
    value=row
    for part in key.split('.'):value=value.get(part) if isinstance(value,dict) else None
    values.append(str(value))
   return values
  if complete and (check_total!=total or sorted(keys(check_rows))!=sorted(keys(first_rows))):complete=False;reason='first_page_changed'
 return {'complete':complete,'coverage':'requested_list_snapshot' if complete else 'partial_pages',
  'stop_reason':reason,'pages_fetched':len(pages),'unique_count':len(seen),'official_total':total,
  'next_page':len(pages)+1 if reason=='max_pages' else None,'raw_pages':pages,'verification_first_page':verification,'failure':failure,
  'notes':['完整性仅针对所选日期、活动和筛选的列表；不证明持续稳定或全店覆盖。']}


def collect(args):
 from .cli import load_taobao_cookies,_api_get
 from ...core import transport
 options=dict(start=args.date,end=args.end_date,tool=args.tool,method=args.method,
  device=args.device,index=args.index,page=args.page,limit=args.limit,activity_id=args.activity_id,item_id=args.item_id,act_status=args.act_status,
  act_type=args.act_type,act_range=args.act_range,keyword=args.keyword,category_id=args.category_id,refund_date_type=args.refund_date_type,
  period=args.period,compare_start=args.compare_start,compare_end=args.compare_end,compare_category_id=args.compare_category_id,benchmark=args.benchmark,sort_by=args.sort_by,sort_order=args.sort_order)
 options=pagination_options(args.report,options,args.all_pages)
 path,params,scope=build_request(args.report,**options)
 page_key=None
 if args.all_pages:
  if args.page!=1:raise ValueError('全量分页必须从第一页开始')
  if args.report=='marketing-tool-activities' and args.tool!='spsd4kefu':page_key='actId'
  if args.report=='marketing-activity-items' and args.tool=='commonItemPromotion':page_key='itemId'
  if args.report=='sales-category-leaf':page_key='cateId'
  if args.report=='marketing-method-items' and args.method=='gouwujin':page_key='itemId.value'
  if args.report=='marketing-method-skus' and args.method=='gouwujin':page_key='skuId.value'
  if not page_key:raise ValueError('该报表尚无已核对的全量分页契约；请保留单页查询')
 cookies=load_taobao_cookies();client=cookies.client
 referer='https://sycm.taobao.com'+('/cc/video/analysis' if args.report.startswith('video-') else '/ipoll/index.htm' if args.report.startswith('realtime-') else '/fa/refund/analysis' if args.report.startswith('refund-') else '/fa/trade/detail' if args.report.startswith('sales-') else '/xsite/promotion/promotion/sales')
 result={'source':'shopdate_symc_MCP_extension','observed_at':datetime.now(timezone(timedelta(hours=8))).isoformat(),
  'report':args.report,'request':{'path':path,'params':params,'referer':referer},'time_scope':scope,
  'source_basis':{'op-live':'5.0.90','op-sales':'1.0.95','op-fa':'1.0.36','ops-bda':'1.0.15',
   'refund_live_schema':'SYCM_ABJwktf8','refund_close_schema':'SYCM_daJ8A2dC','refund_reason_schema':'SYCM_3LkTBIAp','video_overview_schema':'SYCM_AdBHhF2i'},'status':'error'}
 try:
  if not getattr(client,'_bridge_server',None):raise ValueError('新增查询仅允许 extension-backed MCP，不使用 Cookie/直连接口回退')
  result['bridge_diagnostics']=[]
  with trace_bridge(client._bridge_server,result['bridge_diagnostics']):
   result['phase']='token_read'
   token=cookies.get('_tb_token_','')
   result['phase']='api_request'
   def fetch(page):
    _,p,_=build_request(args.report,**{**options,'page':page})
    return _api_get(path,{**p,'_':str(int(time.time()*1000)),'token':token},cookies,referer=referer)
   if args.report=='refund-close-trend':
    first,last=(date.fromisoformat(v) for v in params['dateRange'].split('|'))
    def fetch_day(day):
     _,p,_=build_request('refund-close-overview',**{**options,'start':day.isoformat(),'end':day.isoformat(),'period':'day','compare_start':None,'compare_end':None})
     return _api_get(path,{**p,'_':str(int(time.time()*1000)),'token':token},cookies,referer=referer)
    result.update(daily_refunds(fetch_day,first,last));response=None
   elif page_key:
    result['pagination']=paginate(fetch,page_key,args.max_pages)
    response=result['pagination']['raw_pages'][0]
   else:response=fetch(args.page)
   if args.period=='compareRange' and args.report=='marketing-method-overview':
    compare_options={**options,'start':args.compare_start,'end':args.compare_end,'compare_start':args.date,'compare_end':args.end_date}
    compare_path,compare_params,_=build_request(args.report,**compare_options)
    result['comparison']={'request':{'path':compare_path,'params':compare_params},'status':'error'}
    try:
     compare_raw=_api_get(compare_path,{**compare_params,'_':str(int(time.time()*1000)),'token':token},cookies,referer=referer)
     result['comparison'].update(raw=compare_raw,summary=summarize(compare_raw),status=summarize(compare_raw)['data_status'])
    except Exception as error:result['comparison']['error_type']=type(error).__name__
  result['phase']='response_validation'
  if args.report!='refund-close-trend':
   result['raw']=response;result['summary']=report_summary(args.report,response,params);result['status']=result['summary']['data_status']
  if 'comparison' in result:
   result['summary']['comparison_status']=result['comparison']['status']
   result['summary']['notes'].append('双区间分别复用同一官方汇总接口；保存两次响应，不自行补造官方未返回的对比率。自定义人群指标可能是单日相加，遵循官方口径。')
   if result['comparison']['status'] not in ('ok','no_data'):result['status']='partial';result['summary']['data_status']='partial'
  if args.period=='compareRange' and args.report=='marketing-method-trend':
   result['summary']['notes'].append('官方自定义趋势实测返回截至当前区间结束日的30天序列；不代表仅请求区间，不生成未返回的对比区间曲线。')
  if page_key:
   result['summary']['first_page_row_count']=result['summary'].get('row_count')
   result['summary'].update({k:v for k,v in result['pagination'].items() if k not in ('raw_pages','verification_first_page')})
   result['summary']['row_count']=result['pagination']['unique_count']
   if not result['pagination']['complete']:result['status']='partial';result['summary']['data_status']='partial'
 except Exception as error:
  result['error']=str(error)
  raise
 finally:
  if args.out:
   p=Path(args.out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
  transport.release(client)
 print(json.dumps(result if not args.out else {'status':result['status'],'report':args.report,'summary':result['summary'],'out':args.out},ensure_ascii=False,indent=2))


def catalog(args):
 validation_file=Path(__file__).with_name('business_query_validation.json')
 validation=json.loads(validation_file.read_text(encoding='utf8')) if validation_file.is_file() else {'status':'not_available'}
 print(json.dumps({'reports':REPORTS,'tools':{k:v[0] for k,v in TOOLS.items()},'methods':METHODS,'excluded_or_gaps':EXCLUDED,
  'declared_periods':{report:({method:supported_periods(report,method) for method in METHODS} if report.startswith('marketing-method-') else supported_periods(report)) for report in REPORTS},
  'existing_reused':['macro-monitor','item-list','cate-list','new-product-list','new-product-overview','new-product-trend','item-relate','video-list','sale-shop-list','refund-item-list','refund-all-list','refund-origin-analysis'],
  'latest_validation':validation,
  'acceptance':'Implemented fixed query is not proof of live field or full-page coverage. See dated module acceptance evidence.'},ensure_ascii=False,indent=2))


def register(sp):
 sp.add_parser('business-catalog',help='营销、交易和商品接入目录与明确缺口（不取数）').set_defaults(func=catalog)
 p=sp.add_parser('business-query',help='官方固定营销工具/玩法、交易实时与销售分析只读查询')
 p.add_argument('--report',choices=tuple(REPORTS),required=True)
 p.add_argument('--date');p.add_argument('--end-date');p.add_argument('--tool',choices=tuple(TOOLS),default='commonItemPromotion')
 p.add_argument('--period',choices=('day','recent7','recent30','week','month','range','compareRange'),help='显式官方周期；自然周/月必须完整；未声明的报表组合拒绝')
 p.add_argument('--compare-start');p.add_argument('--compare-end')
 p.add_argument('--compare-category-id',help='官方同行类目字典ID；不筛选本店销售')
 p.add_argument('--benchmark',choices=('average','excellent'))
 p.add_argument('--sort-by');p.add_argument('--sort-order',choices=('asc','desc'))
 p.add_argument('--method',choices=tuple(METHODS),default='newer');p.add_argument('--device',choices=('0','1','2'))
 p.add_argument('--index');p.add_argument('--page',type=int,default=1);p.add_argument('--limit',type=int,default=10)
 p.add_argument('--activity-id');p.add_argument('--item-id');p.add_argument('--act-status',choices=('0','1'),default='1');p.add_argument('--out')
 p.add_argument('--act-type',choices=('1','2'));p.add_argument('--act-range',choices=('shopPromotionAll','shopPromotionPart'))
 p.add_argument('--keyword');p.add_argument('--category-id')
 p.add_argument('--refund-date-type',choices=('pay',),default='pay')
 p.add_argument('--all-pages',action='store_true');p.add_argument('--max-pages',type=int,default=20)
 p.set_defaults(func=collect)
