"""Official date-picker period codes; complete natural periods only."""
from datetime import date,timedelta
import calendar

def period_params(end,period,start=None):
    from .shop_insights import historical_day
    historical_day(end);last=date.fromisoformat(end)
    if period=='week':
        if last.weekday()!=6:raise ValueError('周查询必须以完整自然周周日为截止日。')
        first=last-timedelta(days=6);year,week,_=first.isocalendar();code=f'99{year}{week:02}'
    elif period=='month':
        if last.day!=calendar.monthrange(last.year,last.month)[1]:raise ValueError('月查询必须以完整自然月末日为截止日。')
        first=last.replace(day=1);code=f'{last.year}{last.month:02}'
    elif period=='quarter':
        if last.month%3 or last.day!=calendar.monthrange(last.year,last.month)[1]:raise ValueError('季度查询必须以完整自然季度末日截止。')
        first=last.replace(month=last.month-2,day=1);code=f'95{last.year}{last.month//3:02}'
    elif period in ('day7','day30'):
        days=7 if period=='day7' else 30;first=last-timedelta(days=days-1);code=str(days)+end
    elif period=='custom':
        historical_day(start);first=date.fromisoformat(start)
        if not 0<=(last-first).days<=30:raise ValueError('自定义区间须1至31天且起止顺序正确。')
        code='10'+end
    else:raise ValueError('未登记的跨周期查询。')
    if start is not None and first.isoformat()!=start:raise ValueError('自然周期起始日期不符。')
    return {'date':code,'startDate':first.isoformat(),'endDate':end,'dateType':'custom' if period in ('day7','day30') else period}

def check_intimacy_range(data,params):
    from .shop_insights import historical_day
    if not isinstance(data,dict):raise ValueError('缺少官方亲密度可查日期。')
    low=data.get('startDate');high=data.get('endDate')
    for value in (low,high):
        if not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value:raise ValueError('亲密度可查日期无效。')
    if not low<=params['startDate']<=params['endDate']<=high:raise ValueError('亲密度仅支持官方当前近三周范围：'+low+' 至 '+high+'。')
    return {'official_start':low,'official_end':high,'requested_start':params['startDate'],'requested_end':params['endDate']}


def check_industry_access(auth,categories=None,params=None):
    rows=auth.get('data') if isinstance(auth,dict) else None
    if not isinstance(rows,list) or len(rows)!=1 or not isinstance(rows[0],dict) or rows[0].get('DataVip') is not True:raise ValueError('官方会员行业数据未明确授权，停止行业查询。')
    if categories is None:return {'authorized':True}
    data=categories.get('data') if isinstance(categories,dict) else None
    tree=data.get('category') if isinstance(data,dict) else None
    if not isinstance(tree,list):raise ValueError('官方会员行业类目字典结构无效。')
    def find(nodes):
        for node in nodes:
            if not isinstance(node,dict):continue
            if str(node.get('id'))==params['secondIndId'] and any(isinstance(c,dict) and str(c.get('id'))==params['thirdIndId'] for c in node.get('children') or []):return True
            if find(node.get('children') or []):return True
        return False
    if not find(tree):raise ValueError('所选二三级类目不在官方行业字典同一父子关系中。')
    return {'authorized':True,'second_id':params['secondIndId'],'third_id':params['thirdIndId']}
