"""Deterministic overview calculations. No platform clients or network access."""
from datetime import date, datetime, timedelta, timezone
import math
import re
from statistics import median

VERSION = '1'
CN = timezone(timedelta(hours=8))
JD_AMOUNT = 'jdr_sch_trade_deal_ord_ord_amt_sz_trade_deal_snapshot'
JD_BUYERS = 'jdr_sch_user_deal_ord_user_cnt_sz_user_deal_snapshot'
JD_UV = 'jdr_sch_traffic_enter_shop__browse_page_cnt_shop_last_src'
DEFINITIONS = {
    'symc': [
        ('payAmt','支付金额','元','sum'), ('netPaymentAmount','净支付金额','元','sum'),
        ('uv','访客数','人','uv'), ('payByrCnt','支付买家数','人','buyers'),
        ('payRate','支付转化率','fraction','ratio'), ('payPct','客单价','元','ratio'),
        ('pv','浏览量','次','sum'), ('subPayOrdSubCnt','支付子订单数','单','sum'),
        ('payItmCnt','支付件数','件','sum'), ('cartByrCnt','加购人数','人','people'),
        ('cltItmCnt','商品收藏人数','人','people'),
        ('rfdSucAmt','退款金额(完结时间)','元','sum'),
        ('payAmtRfdRate','金额退款率','fraction','ratio'),
        ('ordRfdRate','订单退款率','fraction','ratio'),
        ('realPayrealRfdRate','签收退款率','fraction','ratio'),
        ('p4pExpendAmt','关键词推广费','元','sum'),
        ('cubeAmt','精准人群推广费','元','sum'), ('feedCharge','智能场景花费','元','sum'),
        ('adStrategyAmt','全站推广花费','元','sum'), ('tkExpendAmt','淘宝客佣金','元','sum')],
    'jd': [
        (JD_AMOUNT,'成交金额','元','sum'), (JD_BUYERS,'成交客户数','人','buyers'),
        (JD_UV,'店铺访客数','人','uv'), ('fo_jdr_sch_shop_deal_rate','店铺成交转化率','fraction','ratio'),
        ('fo_jdr_sch_trade_deal_ord_amt_user_sz_trade_deal_snapshot','客单价','元','ratio'),
        ('jdr_sch_trade_deal_ord_sku_qtty_sz_trade_deal_snapshot','成交商品件数','件','sum'),
        ('jdr_sch_trade_deal_ord_ord_qtty_sz_trade_deal_snapshot','成交单量','单','sum'),
        ('jdr_sch_traffic_enter_shop__browse_page_qtty_shop_last_src','店铺浏览量','次','sum'),
        ('fo_jdr_sch_trade_cancel_refund_ord_amt','退款金额','元','sum')]
}
CORE = {'symc':['payAmt','netPaymentAmount','uv','payByrCnt','payRate','payPct'],
        'jd':[JD_AMOUNT, JD_BUYERS, JD_UV, 'fo_jdr_sch_shop_deal_rate',
              'fo_jdr_sch_trade_deal_ord_amt_user_sz_trade_deal_snapshot']}


def numeric(value):
    return value if type(value) in (int,float) and math.isfinite(value) else None


def ratio(a,b):
    return numeric(a/b) if a is not None and b not in (None,0) else None


def window(platform, store, day, task, today=None):
    if platform not in DEFINITIONS or task not in ('daily','weekly'):
        raise ValueError('只支持jd/symc平台及daily/weekly基础任务。')
    pattern = r'jd:mall:\d+' if platform == 'jd' else r'sycm:account:\d+'
    if not re.fullmatch(pattern,store):
        raise ValueError('必须使用对应平台的精确store_key，不能使用昵称。')
    target = date.fromisoformat(day)
    if target.isoformat()!=day or target >= (today or datetime.now(CN).date()):
        raise ValueError('仅支持北京时间历史完整日，日期格式YYYY-MM-DD。')
    count = 7 if task=='daily' else 14
    return [(target-timedelta(days=i)).isoformat() for i in range(count-1,-1,-1)]


def analyze(platform, store, day, task, rows, today=None):
    dates = window(platform,store,day,task,today)
    if len(rows)!=len(dates) or sorted(r['date'] for r in rows)!=dates:
        raise ValueError('日期必须连续完整且无重复。')
    ordered=sorted(rows,key=lambda r:r['date'])
    if any(r.get('platform')!=platform or r.get('store_key')!=store for r in ordered):
        raise ValueError('平台或店铺身份不一致。')
    if platform=='jd':
        for index,row in enumerate(ordered):
            if row.get('compare_date')!=(date.fromisoformat(row['date'])-timedelta(days=1)).isoformat() or not isinstance(row.get('comparisons'),dict):
                raise ValueError('京东证据缺少官方对比日期或比较值，需重新取得或核验原始证据。')
            if not index:
                continue
            for field,_,unit,_ in DEFINITIONS['jd']:
                previous=numeric(row['comparisons'].get(field))
                preceding=numeric(ordered[index-1]['values'].get(field))
                tolerance=.01 if unit=='元' else 1e-8 if unit=='fraction' else 0
                if previous is not None and preceding is not None and not math.isclose(previous,preceding,rel_tol=0,abs_tol=tolerance):
                    raise ValueError('相邻日期指标不一致：'+row['date']+' '+field+'；需核对平台回补。')
    missing = {field:[r['date'] for r in ordered if numeric(r['values'].get(field)) is None]
               for field,_,_,_ in DEFINITIONS[platform]}
    def values(field):
        return [numeric(r['values'].get(field)) for r in ordered]
    def totals(field):
        v=values(field)
        return [sum(g) if all(x is not None for x in g) else None for g in (v[:7],v[7:])]
    metrics=[]
    def append(field,name,unit,value,previous,definition,kind='calculated',**extra):
        change=ratio(value,previous)
        metrics.append(dict(field=field,name=name,unit=unit,value=value,previous=previous,
            relative_change=change-1 if change is not None else None,
            kind=kind,definition=definition,**extra))
    for field,name,unit,aggregation in DEFINITIONS[platform]:
        v=values(field)
        if task=='daily':
            baseline=median(v) if all(x is not None for x in v) else None
            relative=ratio(v[-1],baseline)
            append(field,name,unit,v[-1],v[-2],'平台官方同名日指标；比较及中位数为本次计算',
                'official',median7=baseline,valid_days=sum(x is not None for x in v),
                vs_median7=relative-1 if relative is not None else None,
                formula='D与D-1比较；median(D-6..D)，包含目标日')
        elif aggregation!='ratio':
            previous,value=totals(field)
            definition='sum(日官方同名指标)，缺一日则不计算'
            if aggregation=='uv':
                previous,value=ratio(previous,7),ratio(value,7)
                name='日均'+name; definition='sum(日UV)/7；不是区间去重UV'
            if aggregation in ('buyers','people'):
                name += '（逐日加总人次）'; unit='人次'
                definition+='；跨日可能重复，不是区间去重人数'
            append('buyer_day_count' if aggregation=='buyers' else field,
                   name,unit,value,previous,definition)
    if task=='weekly':
        amount,buyers,uv=('payAmt','payByrCnt','uv') if platform=='symc' else (JD_AMOUNT,JD_BUYERS,JD_UV)
        for field,name,numerator,denominator,unit in [
            ('daily_weighted_cvr','按日汇总近似转化率',buyers,uv,'fraction'),
            ('daily_weighted_aov','按日汇总客单价',amount,buyers,'元')]:
            ns,ds=totals(numerator),totals(denominator)
            append(field,name,unit,ratio(ns[1],ds[1]),ratio(ns[0],ds[0]),
                   '按日汇总近似；不是原生区间去重口径',
                   formula=f'sum({numerator})/sum({denominator})',
                   numerator={'field':numerator,'previous':ns[0],'value':ns[1]},
                   denominator={'field':denominator,'previous':ds[0],'value':ds[1]})
    core_missing={f:missing[f] for f in CORE[platform] if missing[f]}
    result=dict(schema_version=VERSION,workflow=task,platform=platform,store_key=store,
        date=day,timezone='Asia/Shanghai',status='partial' if core_missing else 'ok',
        current_period=[dates[-1] if task=='daily' else dates[7],dates[-1]],
        previous_period=[dates[0],dates[6]] if task=='weekly' else [dates[-2],dates[-2]],
        baseline_period=[dates[0],dates[-1]] if task=='daily' else None,
        metrics=metrics,deduplicated_period_uv=None,
        quality={'core_missing':core_missing,'missing_by_field':{f:d for f,d in missing.items() if d}},
        coverage={'scope':'overview_only','requested_days':len(dates),
                  'received_days':len(ordered),'not_included':['商品来源下钻','订单队列归因','广告归因','经营原因判断']},
        signals=[],limitations=['ok仅表示基础概况核心指标通过，不代表完整经营分析。',
          '退款事件可能跨期，不推算同期真实退货率；平台间指标不强制合并。',
          '缺失不补零；周比例不平均每日比例。'])
    from .signals import build_signals
    result['signals'],result['drilldown_requests']=build_signals(result)
    return result
