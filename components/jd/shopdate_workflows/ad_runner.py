"""Ad fresh/replay/resume orchestration; never modifies merchant data."""
from datetime import datetime,timezone,timedelta
import json
from pathlib import Path
import time
from uuid import uuid4
from .ad_review import analyze_ads
from .evidence import read_evidence,write_evidence,save_json
from .metrics import window
from .metrics import CN

ROOT=Path(__file__).resolve().parents[1]


def load_category_cache(base,store,*,now=None,max_age_days=7):
    """Reuse only recent, identity-verified official mappings, never ad metrics."""
    now=now or datetime.now(timezone.utc)
    folder=Path(base)/'symc'/store.replace(':','_')
    candidates=sorted(folder.glob('*/ad-review/*/evidence.json'),
                      key=lambda path:path.stat().st_mtime,reverse=True)[:12]
    selected={};sources=[]
    for path in candidates:
        try:
            payload=read_evidence(path,'symc',store)
            if payload.get('identity_verified') is not True:continue
            used=False
            for item in payload.get('items',[]):
                if item.get('category_mapping_source')!='/cc/item/price/info.json':continue
                identifier=str(item.get('id',''));category=item.get('category_id');names=item.get('official_path')
                if not identifier.isdigit() or not category or not isinstance(names,list) or not names or not all(isinstance(x,str) and x for x in names):continue
                observed=item.get('category_observed_at')
                if not isinstance(observed,str):continue
                stamp=datetime.fromisoformat(observed)
                if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=CN)
                if not timedelta(0)<=now-stamp<=timedelta(days=max_age_days):continue
                if identifier not in selected or stamp>selected[identifier][0]:
                    selected[identifier]=(stamp,{key:item[key] for key in (
                        'id','category_id','official_path','category_observed_at')})
                    used=True
            if used:sources.append(str(path.resolve()))
        except (ValueError,KeyError,TypeError,OSError,OverflowError):
            continue
    if not selected:return None
    return {'platform':'symc','store_key':store,'identity_verified':True,
            'items':[entry[1] for _,entry in sorted(selected.items())],
            'provenance':{'type':'automatic_official_category_cache','files':sources,
                          'max_age_days':max_age_days,'observation_time_preserved':True}}


def markdown(report):
    def fmt(value,percent=False):
        return '缺失/不可计算' if value is None else f'{value:.2%}' if percent else f'{value:,.2f}'
    lines=['# shopdate 广告固定复盘','',f"日期：{report['date']}；店铺：{report['store_key']}",
        f"状态：{report['status']}；身份：{report['quality']['identity_status']}；归因窗口：{report['attribution']['window_days']}天。",
        '', '| 渠道 | 花费 | 花费SOB | ROI | 归因转化率 |','|---|---:|---:|---:|---:|']
    for row in report['channels']:
        lines.append('| '+row['name']+' | '+' | '.join([fmt(row['spend']),fmt(row['spend_sob'],True),fmt(row['roi']),fmt(row['cvr'],True)])+' |')
    if report.get('plans'):
        lines+=['','| 广告计划 | 计划ID | 花费 | ROI | 归因转化率 |','|---|---|---:|---:|---:|']
        for row in report['plans']:
            lines.append('| '+row['name']+' | '+row['id']+' | '+fmt(row['spend'])+' | '+fmt(row['roi'])+' | '+fmt(row['cvr'],True)+' |')
    lines+=['','| 官方类目分组 | 花费 | 花费SOB | 实际销售 | 销售SOB | 广告费率 |','|---|---:|---:|---:|---:|---:|']
    for row in report['categories']:
        lines.append('| '+row['name']+' | '+' | '.join([fmt(row['spend']),fmt(row['spend_sob'],True),fmt(row['sales']),fmt(row['sales_sob'],True),fmt(row['ad_spend_rate'],True)])+' |')
    lines+=['','| 官方销售明细路径 | 实际销售 | 销售SOB |','|---|---:|---:|']
    for row in report['sales_details']:
        lines.append('| '+row['name']+' | '+fmt(row['sales'])+' | '+fmt(row['sales_sob'],True)+' |')
    lines+=['','质量验收：','```json',json.dumps(report['quality'],ensure_ascii=False,indent=2),'```',
            '',*['- '+note for note in report['limitations']],
            '- 归因转化率为alipayInshopNum/click，不是去重买家转化率。',
            f"- 证据：{report['evidence']['path']}"]
    return '\n'.join(lines)+'\n'


def run_ads(store,day,evidence_path=None,legacy_dir=None,output_root=None,resume_path=None,
            category_evidence_path=None,category_limit=20,refresh=False):
    window('symc',store,day,'daily')
    if sum(bool(x) for x in (evidence_path,legacy_dir,resume_path))>1:
        raise ValueError('广告重放、旧快照导入、续跑只能选择一种。')
    if (evidence_path or legacy_dir) and (category_evidence_path or refresh):
        raise ValueError('离线证据重放/导入不能使用新取数参数。')
    mode='legacy_import' if legacy_dir else 'replay' if evidence_path else 'live_refresh' if refresh else 'live_resume' if resume_path else 'live'
    tick=time.perf_counter()
    base=Path(output_root).resolve() if output_root else ROOT/'data/workflows'
    folder=base/'symc'/store.replace(':','_')/day/'ad-review'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex[:8])
    if legacy_dir:
        from .legacy_ads import import_snapshot
        payload=import_snapshot(legacy_dir,store,day)
        evidence_path=folder/'evidence.json'
        write_evidence(evidence_path,payload)
    elif evidence_path:
        evidence_path=Path(evidence_path).resolve()
        payload=read_evidence(evidence_path,'symc',store)
    else:
        from .ad_source import acquire
        from .ad_source_live import Provider
        state=None
        if resume_path and not refresh:
            state=read_evidence(resume_path,'symc',store).get('acquisition_state')
            if state is None:raise ValueError('此证据没有广告新取数检查点，不能续跑。')
        cache_started=time.perf_counter()
        category_seed=(read_evidence(category_evidence_path,'symc',store) if category_evidence_path
                       else load_category_cache(base,store))
        cache_ms=round((time.perf_counter()-cache_started)*1000)
        evidence_path=folder/'evidence.json'
        def checkpoint(state):
            write_evidence(evidence_path,{'platform':'symc','store_key':store,'date':day,
                'identity_verified':False,'acquisition_state':state})
        provider=Provider()
        try:
            payload=acquire(provider,store,day,state=state,save=checkpoint,
                category_limit=category_limit,category_seed=category_seed)
        except Exception as error:
            save_json(folder/'failure.json',{'status':'failed','date':day,'store_key':store,
                'error':str(error),'checkpoint':str(evidence_path),'automatic_retry':False})
            raise
        if category_evidence_path:
            payload['provenance']['category_evidence']={'path':str(Path(category_evidence_path).resolve()),
                'sha256':json.loads(Path(category_evidence_path).read_text(encoding='utf-8'))['sha256']}
        elif category_seed:
            payload.setdefault('provenance',{})['automatic_category_cache']={
                **category_seed['provenance'],'available_items':len(category_seed['items']),
                'load_ms':cache_ms}
        payload['source_requests_this_call']=provider.requests
        write_evidence(evidence_path,payload)
    report=analyze_ads(payload,store,day)
    report['evidence']={'path':str(evidence_path),
        'sha256':json.loads(Path(evidence_path).read_text(encoding='utf-8'))['sha256']}
    report['provenance']=payload.get('provenance',{})
    report['collection']={'mode':mode,
        'source_requests_this_call':payload.get('source_requests_this_call',0) if mode.startswith('live') else 0,
        'pending_category_ids':payload.get('pending_category_ids',[]),
        'note':'请求数不含平台预检和账号检查；复用的官方类目保留原观察时间。'}
    if report['collection']['pending_category_ids'] and not legacy_dir:
        report['next_call']={'platform':'symc','task':'ad-review','date':day,'store':store,
            'resume_path':str(evidence_path),'category_limit':category_limit or 20}
    report['report_path']=str(folder/'report.json');report['markdown_path']=str(folder/'report.md')
    report['timings']={'total_ms':round((time.perf_counter()-tick)*1000)}
    save_json(folder/'report.json',report)
    (folder/'report.md').write_text(markdown(report),encoding='utf-8')
    return {key:report[key] for key in ('status','workflow','platform','store_key','date','analysis_ready',
        'quality','controls','collection','timings','report_path','markdown_path','evidence','next_call') if key in report}
