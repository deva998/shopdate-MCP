"""Native read-only rival drilldown contracts from official op-market 65/66."""
from datetime import date,datetime,timezone,timedelta
from . import market_queries as market

REPORTS={
 'rival-shop-profile':('ci_shop','/mc/mq/rivalShop/profile/detail.json'),
 'rival-shop-crowd':('ci_shop','/mc/mq/rivalShop/analysis/getShopCrowd.json'),
 'rival-shop-keywords':('ci_shop','/mc/mq/rivalShop/analysis/getSearchWords.json'),
 'rival-shop-products':('ci_shop','/mc/mq/rivalShop/analysis/getTopItems/page.json'),
 'rival-item-keywords':('ci_item','/mc/mq/rivalItem/analysis/getSearchWords.json'),
 'rival-item-detail-core':('ci_item','/mc/mq/rivalItem/itemDetail/analysis/getCoreIndexes.json'),
 'rival-item-detail-trend':('ci_item','/mc/mq/rivalItem/itemDetail/analysis/getCoreTrend.json'),
 'rival-item-detail-list':('ci_item','/mc/mq/rivalItem/itemDetail/analysis/list.json'),
 'rival-item-material':('ci_item','/mc/mq/rivalItem/itemDetail/main/pic/analysis/material.json'),
 'rival-item-recommend-core':('ci_item','/mc/mq/rivalItem/recommendedMaterials/analysis/getCoreIndexes.json'),
 'rival-item-recommend-trend':('ci_item','/mc/mq/rivalItem/recommendedMaterials/analysis/trend.json'),
 'rival-item-recommend-top':('ci_item','/mc/mq/rivalItem/recommendedMaterials/analysis/top.json'),
}
DETAIL_METRICS=('itemExposeUv','itemInteractUv','itemCartConvertRate','itemPayConvertRate','itemLossRate')
RECOMMEND_METRICS=('clickExpRateNew','ndUv','deepViewCtr','detailViewCtr','allFirstPayUv')
SORTS={
 'rival-shop-keywords':('uv','payByrCnt','payRate'),
 'rival-item-keywords':('uv','payByrCnt','payRate'),
 'rival-shop-products':('uv','payByrCnt'),
 'rival-item-detail-list':DETAIL_METRICS,
 'rival-item-material':DETAIL_METRICS,
 'rival-item-recommend-top':('clickExpRateNew','deepViewCtr','detailViewCtr'),
}

def build_params(args,identifier,params):
 r=args.report;metric=getattr(args,'metric',None);audience=getattr(args,'audience',None)
 if args.date_type not in ('day','week','month'):raise ValueError('Only native day/week/month contracts are supported for these drilldowns')
 if metric is not None and (r not in SORTS or metric not in SORTS[r]):raise ValueError('Metric is not an official sort option for this report')
 if audience is not None and (r not in ('rival-shop-profile','rival-shop-crowd') or audience not in ('uv','payByrCnt')):raise ValueError('Audience selection only applies to official visitor/buyer profiles')
 p=dict(params)
 if r=='rival-shop-products':p.update(rivalUserId=identifier,topType=metric or 'uv',orderBy=metric or 'uv',page=1,pageSize=10)
 elif r.startswith('rival-shop-'):
  p['rivalUser1Id']=identifier
  if r in ('rival-shop-profile','rival-shop-crowd'):p.update(rivalUser2Id='',topType=audience or 'uv')
  else:p.update(orderBy=metric or 'uv',order='desc',page=1,pageSize=10)
 else:
  p['rivalItem1Id']=identifier
  if r in ('rival-item-detail-core','rival-item-detail-trend','rival-item-detail-list','rival-item-recommend-core','rival-item-recommend-trend'):p.update(rivalItem2Id='',selfItemId='')
  if r.endswith('-trend'):p['device']=0
  if r in SORTS:
   chosen=metric or SORTS[r][0];p['orderBy']=chosen
   if r!='rival-item-keywords':p['order']='asc' if r=='rival-item-material' and chosen=='itemLossRate' else 'desc'
   if r!='rival-item-detail-list':p.update(page=1,pageSize=10)
 return p

def annotate_period(summary,params):
 s=dict(summary);start,end=params['dateRange'].split('|')
 s.update(requested_period=params['dateRange'],requested_date_type=params['dateType'],date_verified=False,period_aggregation_verified=False,period_axis_status='not_independently_verified')
 if s['data_status'] not in ('ok','partial','date_mismatch'):return s
 dates=s.get('returned_dates') or []
 outside=[v for v in dates if not start.replace('-','')<=v.replace('-','')<=end.replace('-','')]
 if outside:s.update(data_status='date_mismatch',out_of_period_dates=outside,period_axis_status='out_of_period_date_echo')
 elif dates:s['period_axis_status']='period_date_echo_only'
 axes=s.get('trend_axes') or {}
 native_dates=sorted({day for axis in axes.values() for day in axis.get('dates',[])})
 if native_dates:
  s['period_axis_status']='native_trend_window_outside_requested_period' if native_dates[0]<start or native_dates[-1]>end else 'native_trend_dates_within_requested_period'
  s['native_trend_range']=[native_dates[0],native_dates[-1]]
  checks={}
  for name,axis in axes.items():
   ticks=[date.fromisoformat(v) for v in axis.get('dates',[])]
   valid=len(ticks)>=2 and ticks[-1].isoformat()==end
   if params['dateType']=='week':valid=valid and all(v.weekday()==6 for v in ticks) and all((b-a).days==7 for a,b in zip(ticks,ticks[1:]))
   elif params['dateType']=='month':valid=valid and all((v+timedelta(days=1)).month!=v.month for v in ticks) and all((b.year*12+b.month)-(a.year*12+a.month)==1 for a,b in zip(ticks,ticks[1:]))
   else:valid=False
   checks[name]=valid
  s.update(native_tick_frequency=params['dateType'],native_tick_frequency_verified=bool(checks) and all(checks.values()),native_tick_checks=checks)
 return s

def summarize(raw,report,day):
 # Caller performs common official error/security/missing-payload checks first.
 data=raw['data'];empty=[];records=[]
 if report.endswith('-trend'):
  axes={};invalid=[];metrics=DETAIL_METRICS if report=='rival-item-detail-trend' else RECOMMEND_METRICS
  def visit(x,path):
   if not isinstance(x,dict):return
   if not x:empty.append(path);return
   if isinstance(x.get('statDate'),list):
    dates=x['statDate'];valid=[]
    for key in metrics:
     if key not in x:continue
     values=x[key].get('value') if isinstance(x[key],dict) else None
     if not isinstance(values,list) or len(values)!=len(dates):invalid.append(path+'.'+key)
     elif values:valid.append(key)
    if not dates:
     if not any(k.startswith(path+'.') for k in invalid):empty.append(path)
     return
    try:
     if any(isinstance(t,bool) or not isinstance(t,(int,float)) or not 1000000000000<=t<=4102444800000 for t in dates):raise ValueError('Invalid native date axis')
     axis=[datetime.fromtimestamp(t/1000,timezone(timedelta(hours=8))).date().isoformat() for t in dates]
    except (ValueError,OverflowError,OSError):invalid.append(path+'.statDate');return
    if valid:axes[path]={'points':len(dates),'dates':axis,'metrics':valid}
   else:
    for k,v in x.items():visit(v,path+'.'+k if path else k)
  visit(data,'')
  return {'data_status':'partial' if invalid else 'ok' if axes else 'no_data','complete':False,'date_verified':False,'requested_day':day,'trend_axes':axes,'invalid_sections':invalid,'empty_sections':empty,'coverage':'native_returned_trend_points','notes':['Only native value arrays are statistical values; drawValue is never substituted.']}
 if isinstance(data,list):return market.summarize_market(raw,kind='statistics',day=day)
 if not isinstance(data,dict):return {'data_status':'partial','complete':False,'date_verified':False,'reason':'Unexpected native drilldown shape'}
 # Flatten only documented object/distribution sections for counting and date
 # checks; retain the original response separately, without summing proportions.
 for obj,sections in data.items():
  if not sections:empty.append(obj);continue
  if isinstance(sections,list):records.extend({'object_key':obj,**v} for v in sections if isinstance(v,dict));continue
  if report in ('rival-item-detail-core','rival-item-recommend-core'):
   if isinstance(sections,dict):records.append({'object_key':obj,**sections})
  elif isinstance(sections,dict):
   for key,values in sections.items():
    if values==[] or values=={}:empty.append(obj+'.'+key)
    elif isinstance(values,list):records.extend({'object_key':obj,'section_key':key,**v} for v in values if isinstance(v,dict))
 s=market.summarize_market({**raw,'data':records},kind='statistics',day=day);s.update(empty_sections=empty,coverage='native_returned_sections_only')
 if report=='rival-shop-profile':s['scope']='estimated_gender_age_province_distribution_rows_not_people_count'
 if report=='rival-shop-crowd':s['scope']='estimated_eight_crowd_distribution_rows_not_people_count'
 return s
