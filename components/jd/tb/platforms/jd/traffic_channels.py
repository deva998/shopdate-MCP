"""Official terminal overview, deliberately separate from APP source attribution."""
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
import hashlib,json,re
from .overview import numeric

ROOT=Path(__file__).resolve().parents[3]
PAGE='https://jdsz.jd.com/szweb/view/flow/flow-summary.html'

def contract():
    return json.loads((ROOT/'extension/unpacked/traffic-channel-contract.json').read_text(encoding='utf-8'))

def make_body(day,channel):
    selected=date.fromisoformat(day);spec=contract()
    if channel not in spec['channels']:raise ValueError('未登记的官方终端')
    previous=(selected-timedelta(days=1)).isoformat()
    return {**spec['template'],'startDate':day,'endDate':day,'compareStartDate':previous,'compareEndDate':previous,'channel':channel}

def parse(payload,channel):
    spec=contract()
    if channel not in spec['channels'] or payload.get('header',{}).get('code')!=0 or payload.get('errors'):raise ValueError('流量概况业务状态失败')
    rows=payload.get('body',{}).get('data')
    if not isinstance(rows,list) or len(rows)>1 or (rows and not isinstance(rows[0],dict)):raise ValueError('流量概况应返回单条汇总或明确空表')
    if not rows:return {'channel':channel,'name':spec['channels'][channel],'status':'empty','metrics':{},'missing_metrics':[]}
    metrics={name:{'field':field,'unit':unit,'value':numeric(rows[0].get(field)),
                  'previous':numeric(rows[0].get(field+'##compareValue')),
                  'relative_change':numeric(rows[0].get(field+'##compare'))}
             for name,field,unit in spec['metrics']}
    return {'channel':channel,'name':spec['channels'][channel],'status':'ok','metrics':metrics,
            'missing_metrics':[name for name,value in metrics.items() if value['value'] is None]}

def collect(day,store,*,client=None):
    date.fromisoformat(day)
    if not re.fullmatch(r'jd:mall:\d+',store):raise ValueError('必须指定京东store_key')
    if client is None:
        from .api_client import APIClient
        with APIClient({'platform':'jd','store_key':store},min_extension='0.8.8') as active:return collect(day,store,client=active)
    folder=ROOT/'data/jd'/store.replace(':','_')/day/'traffic-channels'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder.mkdir(parents=True,exist_ok=False)
    channels=[];proofs=[];errors=[]
    for channel in contract()['channels']:
        try:
            payload,proof=client.request('traffic-channel',day,scope={'channel':channel})
            raw=client.last_response_text
            if proof.get('identity',{}).get('store_key')!=store or proof.get('identity',{}).get('platform')!='jd' or proof.get('request_body')!=make_body(day,channel):raise ValueError('终端响应店铺或请求范围不符')
            if not isinstance(raw,str) or hashlib.sha256(raw.encode()).hexdigest()!=proof.get('response_sha256'):raise ValueError('终端响应原文哈希不符')
            path=folder/(channel+'.json');path.write_text(raw,encoding='utf-8')
            proofs.append({**proof,'channel':channel,'response_path':str(path)})
            channels.append(parse(payload,channel))
        except (ValueError,RuntimeError,OSError,TimeoutError) as error:
            errors.append({'channel':channel,'error':str(error)})
            channels.append({'channel':channel,'name':contract()['channels'][channel],'status':'error','metrics':{},'missing_metrics':[]})
            # Do not turn a disconnected bridge or changed account into six
            # repeated waits. The remaining terminals were never requested.
            remaining=list(contract()['channels'])[len(channels):]
            channels.extend({'channel':key,'name':contract()['channels'][key],'status':'not_requested','metrics':{},'missing_metrics':[]} for key in remaining)
            break
    report={'platform':'jd','store_key':store,'date':day,'compare_date':(date.fromisoformat(day)-timedelta(days=1)).isoformat(),
            'status':'partial','source':'registered-api','scope':'official_terminal_overview',
            'terminal_requests_complete':not errors,
            'terminal_metrics_complete':not errors and all(not c['missing_metrics'] for c in channels),
            'terminal_overview_complete':not errors and all(not c['missing_metrics'] for c in channels),
            'all_channels_source_complete':False,'non_app_source_status':'not_available_in_verified_official_page',
            'channels':channels,'requests':proofs,'errors':errors,
            'notes':['全部/APP/PC/微信/手Q/M是终端概况，不是各终端的来源明细。APP来源树仍使用traffic-tree。',
                     '官方新版来源只支持APP；概况页选全部时，其来源卡片也仍为APP，不能冒充全渠道来源。',
                     '全部为官方独立汇总；终端访客不可相加作全店去重人数，不以全部减APP推导非APP来源。',
                     '空表与空值均保留，不补零；不混用店铺访客、商品访客和引入商详访客。',
                     '流量概况成交转化率为成交客户数/商品访客数；不是交易概况的店铺访客转化率。',
                     '该接口可能仅返回当日值和环比比例；未返回的前日绝对值保持空，不按比例反推。',
                     '终端请求全部完成不代表每个终端每项指标均有值，也不代表全终端来源明细已完成。']}
    path=folder/'report.json';report['report_path']=str(path)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    lines=['# 京东商智 · 终端流量概况',f'日期：{day}；店铺：{store}。','',*['- '+n for n in report['notes']],'',
           '| 终端 | 状态 | 店铺访客 | 商品访客 | 成交客户 | 成交金额 |','|---|---|---:|---:|---:|---:|']
    for row in channels:
        vals=[row['metrics'].get(n,{}).get('value') for n in ['店铺访客数','商品访客数','成交客户数','成交金额']]
        lines.append('| '+ ' | '.join([row['name'],row['status'],*['缺失' if v is None else str(v) for v in vals]])+' |')
    (folder/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return {k:v for k,v in report.items() if k!='requests'}
