"""Coordinate sources and calculation; no import of either platform's tb package."""
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from uuid import uuid4
from .evidence import read_evidence, save_json
from .metrics import analyze,window

ROOT=Path(__file__).resolve().parents[1]


def markdown(report):
    lines=['# shopdate 基础'+('日报' if report['workflow']=='daily' else '周报'),'',
        f"平台：{report['platform']}；店铺：{report['store_key']}；目标日：{report['date']}",
        '范围：仅概况。商品、来源和经营原因由助手按需下钻。',
        '本期：'+'—'.join(report['current_period'])+'；对比：'+'—'.join(report['previous_period']), '']
    daily=report['workflow']=='daily'
    lines+=['| 指标 | 本期/当日 | 上期/前日 | 变化 |'+(' 七日中位数 | 较中位数 |' if daily else ''),
            '|---|---:|---:|---:|'+('---:|---:|' if daily else '')]
    def fmt(v,unit):
        if v is None:return '缺失/不可计算'
        return f'{v:.2%}' if unit=='fraction' else f'{v:,.2f}'
    for metric in report['metrics']:
        line='| '+metric['name']+' | '+fmt(metric['value'],metric['unit'])+\
            ' | '+fmt(metric['previous'],metric['unit'])+' | '+fmt(metric['relative_change'],'fraction')+' |'
        if daily:
            line+=' '+fmt(metric['median7'],metric['unit'])+' | '+fmt(metric['vs_median7'],'fraction')+' |'
        lines.append(line)
    lines+=['','口径：',*['- '+m['name']+'：'+m['definition'] for m in report['metrics']],
            '',*['- '+x for x in report['limitations']],
            '',f"证据：{report['evidence']['path']}",f"状态：{report['status']}（仅声明的基础概况范围）"]
    if report.get('signals'):
        lines+=['','观测信号：',*['- '+s['observation'] for s in report['signals']],
            '', '助手按需下钻清单：',*['- '+r['purpose']+'；候选命令：'+', '.join(r['commands']) for r in report.get('drilldown_requests',[])]]
    return '\n'.join(lines)+'\n'


def run(platform,store,day,task,evidence_path=None,output_root=None,resume_path=None,refresh=False):
    started=time.perf_counter()
    window(platform,store,day,task)  # Reject wrong platform/shop/date before network or files.
    if evidence_path and (resume_path or refresh):
        raise ValueError('--evidence重放不能与--resume/--refresh混用。')
    base=Path(output_root).resolve() if output_root else ROOT/'data'/'workflows'
    folder=base/platform/store.replace(':','_')/day/task/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex[:8])
    folder.mkdir(parents=True,exist_ok=True)
    collection_tick=time.perf_counter()
    mode='replay' if evidence_path else 'refresh' if refresh else 'resume' if resume_path else 'fresh'
    if not evidence_path:
        evidence_path=folder/'evidence.json'
        # The CLI/MCP command itself is an isolated worker process. Do not spawn
        # grandchildren that could survive MCP cancellation of that process.
        from .source import collect
        try:
            seed=read_evidence(resume_path,platform,store) if resume_path else None
            collect(platform,store,window(platform,store,day,task),evidence_path,seed=seed,refresh=refresh)
        except Exception as error:
            failure={'status':'failed','platform':platform,'store_key':store,'date':day,
                     'task':task,'error':str(error),'checkpoint':str(evidence_path),
                     'note':'未完成证据不可作为完整分析结果，未启动自动重试。'}
            save_json(folder/'failure.json',failure)
            raise RuntimeError(f"取数失败；诊断保存在 {folder/'failure.json'}：{error}") from error
    evidence_path=Path(evidence_path).resolve()
    payload=read_evidence(evidence_path,platform,store)
    if payload.get('identity_verified') is not True:
        raise ValueError('证据未通过身份核验，禁止作为完整报告证据。')
    collection_ms=round((time.perf_counter()-collection_tick)*1000)
    calculation_tick=time.perf_counter()
    report=analyze(platform,store,day,task,payload['rows'])
    report['collection']={'mode':mode,'acquired_at':payload.get('acquired_at'),
        'overview_request_count':payload.get('overview_request_count') if mode!='replay' else 0,
        'reused_dates':payload.get('reused_dates',[]),'fresh_dates':payload.get('fresh_dates',[]),
        'cached_source_acquired_at':payload.get('cached_source_acquired_at'),
        'note':'概况请求数不含身份检查与辅助接口；复用日期保留原始来源时间，不代表全窗口刷新。'}
    report['evidence']={'path':str(evidence_path),'sha256':json.loads(evidence_path.read_text(encoding='utf-8'))['sha256']}
    report['auxiliary']={'grow_factor':payload.get('grow_factor',{'status':'not_requested'})}
    report['timings']={'collection_ms':collection_ms,
        'calculation_ms':round((time.perf_counter()-calculation_tick)*1000),
        'total_ms':round((time.perf_counter()-started)*1000)}
    report['report_path']=str(folder/'report.json');report['markdown_path']=str(folder/'report.md')
    save_tick=time.perf_counter()
    save_json(folder/'report.json',report)
    (folder/'report.md').write_text(markdown(report),encoding='utf-8')
    report['timings']['save_ms']=round((time.perf_counter()-save_tick)*1000)
    report['timings']['total_ms']=round((time.perf_counter()-started)*1000)
    save_json(folder/'report.json',report)
    return {key:report[key] for key in ('status','platform','store_key','workflow','date',
        'coverage','quality','timings','report_path','markdown_path','evidence')}
