"""Fixed marketing OneService datasets; share verified structural parser only."""
from datetime import date,datetime,timedelta,timezone
import json,re
from pathlib import Path
from uuid import uuid4

CONTRACTS=json.loads((Path(__file__).resolve().parents[3]/'extension/unpacked/business-metric-contracts.json').read_text('utf-8'))


def params(report,day,*,snapshot=None,archive=False):
    c=CONTRACTS[report]
    start=(date.fromisoformat(day)-timedelta(days=c.get('window_days',1)-1)).isoformat()
    tokens={'$DAY':day,'$START':start,'$TRACE':str(uuid4()),'$BATCH':str(uuid4())}
    if c.get('snapshot'):
        now=datetime.now(timezone(timedelta(hours=8)))
        snapshot=(day+' 00:00:00' if archive and day!=now.date().isoformat() else now.strftime('%Y-%m-%d %H:%M:%S')) if snapshot is None else snapshot
        if not isinstance(snapshot,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',snapshot):raise ValueError('直播快照时间无效。')
        at=datetime.strptime(snapshot,'%Y-%m-%d %H:%M:%S').replace(tzinfo=now.tzinfo)
        if at.date().isoformat()!=day or not archive and (not -5<=(now-at).total_seconds()<=60 or day!=now.date().isoformat()):raise ValueError('直播只读今日新鲜快照，历史快照只能重放。')
        tokens['$SNAPSHOT']=snapshot
    def replace(v):
        if isinstance(v,dict):return {k:replace(x) for k,x in v.items()}
        if isinstance(v,list):return [replace(x) for x in v]
        if isinstance(v,str):
            for key,value in tokens.items():v=v.replace(key,value)
        return v
    return replace(c['template'])


def validate(report,values,day,*,archive=False):
    snapshot=None
    if CONTRACTS[report].get('snapshot'):
        filters=values.get('filterList') if isinstance(values,dict) else None
        if not isinstance(filters,list):raise ValueError('直播缺少时间过滤。')
        ends=[f.get('values') for f in filters if isinstance(f,dict) and f.get('propertyName')=='dt' and f.get('op')=='<=']
        if len(ends)!=1 or not isinstance(ends[0],list) or len(ends[0])!=1:raise ValueError('直播时间终点无效。')
        snapshot=ends[0][0]
    expected=params(report,day,snapshot=snapshot,archive=archive)
    if not isinstance(values,dict) or not isinstance(values.get('commonParam'),dict):raise ValueError('营销指标缺少固定查询参数。')
    for key in ('traceId','batchId'):
        v=values['commonParam'].get(key)
        if not isinstance(v,str) or not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',v):raise ValueError('营销指标追踪ID无效。')
        expected['commonParam'][key]=v
    if json.dumps(values,sort_keys=True,ensure_ascii=False)!=json.dumps(expected,sort_keys=True,ensure_ascii=False):raise ValueError('营销指标超出固定只读模板。')
    return values


def parse(raw,report,day=None,*,values=None):
    from .user_metrics import parse as parse_fixed
    result=parse_fixed(raw,report,contract=CONTRACTS[report])
    coverage=result['coverage']
    coverage.update(scope=CONTRACTS[report]['scope'],whole_module_complete=False,
        schema_validation='fixed_oneservice_structure_verified',
        note='固定官方营销指标；原文、空值、警告和缺失列保留。当前只覆盖登记数据集，不代表页面全部选项或商品全集。')
    if CONTRACTS[report].get('unverified_frontend_fields'):
        coverage['unverified_frontend_fields']=CONTRACTS[report]['unverified_frontend_fields']
        coverage['note']+=' 点击率/曝光转化分层依赖额外类目基准，尚未核验前端分层计算；不生成高低水平判断。'
    limit=CONTRACTS[report].get('row_limit')
    if limit and coverage.get('returned_rows',0)>=limit:
        coverage.update(hit_row_limit=True,whole_query_complete=False,all_available_rows_complete=False)
        coverage['note']+=' 返回行数已达到登记容量，不据size等于返回行数宣称全量。'
    if CONTRACTS[report].get('snapshot'):
        coverage.update(current_snapshot=True,full_day_complete=False,whole_query_complete=False,
            source_timezone='Asia/Shanghai',all_available_rows_complete=False,
            note=coverage['note']+' 实时直播截至采集时刻；行数容量见row_limit，不代表SKU全集；分时与累计图共用官方小时查询，不能相加。')
        if not isinstance(values,dict):raise ValueError('直播返回须绑定原快照时间参数。')
        validate(report,values,day,archive=True)
        snapshot=next(f['values'][0] for f in values['filterList'] if f['propertyName']=='dt' and f['op']=='<=')
        coverage.update(snapshot_at=snapshot,requested_start=day+' 00:00:00')
        if report.endswith('-hourly'):
            hours=[r.get('dt') for r in result['data']['rows']]
            if any(not isinstance(h,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:00',h) or not day+' 00:00:00'<=h+':00'<=snapshot for h in hours) or len(set(hours))!=len(hours):raise ValueError('直播小时日期超出快照范围或分组重复。')
            coverage.update(returned_hours=len(hours),current_hour_settled=False)
    if CONTRACTS[report].get('window_days') and day and coverage.get('returned_end') not in (None,day):raise ValueError('营销趋势末日不符。')
    return result
