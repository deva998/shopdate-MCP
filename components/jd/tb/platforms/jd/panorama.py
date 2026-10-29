"""Saved-evidence panorama: exact store/date, explicit gaps, no hidden collection."""
from collections import Counter
from datetime import date,datetime,timedelta,timezone
import hashlib,json,re,time
from pathlib import Path
from .api_client import ROOT,make_job


def load_overview(path,day,store):
    from . import overview,reports
    path=Path(path);report=json.loads(path.read_text(encoding='utf-8'))
    if report.get('store',{}).get('platform')!='jd' or report.get('store',{}).get('store_key')!=store or report.get('date')!=day:raise ValueError('概况身份或日期不符')
    raw=(path.parent/'response.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=report.get('response_sha256'):raise ValueError('概况原文哈希不符')
    expected=overview.summarize(json.loads(raw),overview.make_request(reports.contracts()['overview']['template'],day))
    if expected['metrics']!=report.get('metrics'):raise ValueError('概况指标与原文不一致')
    return {**report,**overview.data_quality(expected['metrics'])}


class SavedTrafficClient:
    def __init__(self,proofs,day,store):self.proofs=proofs;self.day=day;self.store=store;self.offset=0;self.last_response_text=None
    def request(self,key,day,*,scope=None):
        if self.offset>=len(self.proofs):raise ValueError('来源分页证据缺失')
        proof=self.proofs[self.offset];self.offset+=1
        if day!=self.day or proof.get('date')!=day or proof.get('case')!=key or proof.get('identity',{}).get('platform')!='jd' or proof.get('identity',{}).get('store_key')!=self.store or proof.get('source')!='registered-api':raise ValueError('来源证据身份或日期不符')
        expected=make_job(key,day,{'platform':'jd','store_key':self.store},**({'scope':scope} if scope else {}))
        body=json.loads(expected['body']) if expected.get('body') else None
        if scope!=proof.get('scope') or body!=proof.get('request_body'):raise ValueError('来源请求范围不符')
        raw=Path(proof['response_path']).read_text(encoding='utf-8')
        if hashlib.sha256(raw.encode()).hexdigest()!=proof.get('response_sha256'):raise ValueError('来源原文哈希不符')
        self.last_response_text=raw
        return json.loads(raw),proof


def load_traffic(path,day,store,*,root):
    from . import traffic_tree
    saved=json.loads(Path(path).read_text(encoding='utf-8'))
    if saved.get('store',{}).get('store_key')!=store or saved.get('date')!=day or saved.get('channel')!='app':raise ValueError('来源报告身份或范围不符')
    replay=SavedTrafficClient(saved['requests'],day,store)
    # Same pagination/dictionary parser as live capture, with saved raw responses.
    reconstructed=traffic_tree.collect(day,store,client=replay,root=root,persist=False)
    if replay.offset!=len(saved['requests']) or reconstructed['nodes']!=saved.get('nodes') or not reconstructed['app_complete']:raise ValueError('来源报告与完整原文分页不符')
    return saved


def load_terminals(path,day,store):
    """Rebuild every terminal from its exact saved request and raw response."""
    from . import traffic_channels
    path=Path(path);saved=json.loads(path.read_text(encoding='utf-8'))
    previous=(date.fromisoformat(day)-timedelta(days=1)).isoformat()
    if (saved.get('platform')!='jd' or saved.get('store_key')!=store or saved.get('date')!=day
        or saved.get('compare_date')!=previous or saved.get('scope')!='official_terminal_overview'):
        raise ValueError('终端概况身份、日期或范围不符')
    keys=list(traffic_channels.contract()['channels']);proofs=saved.get('requests',[])
    if len(proofs)!=len(keys) or [p.get('channel') for p in proofs]!=keys:
        raise ValueError('六终端请求证据缺失、重复或顺序不符')
    channels=[]
    for channel,proof in zip(keys,proofs):
        if (proof.get('case')!='traffic-channel' or proof.get('date')!=day or proof.get('source')!='registered-api'
            or proof.get('identity',{}).get('platform')!='jd' or proof.get('identity',{}).get('store_key')!=store
            or proof.get('request_body')!=traffic_channels.make_body(day,channel)):
            raise ValueError('终端请求身份、日期或渠道范围不符')
        raw=Path(proof['response_path']).read_text(encoding='utf-8')
        if hashlib.sha256(raw.encode()).hexdigest()!=proof.get('response_sha256'):raise ValueError('终端原文哈希不符')
        channels.append(traffic_channels.parse(json.loads(raw),channel))
    if channels!=saved.get('channels'):raise ValueError('终端指标与原文不一致')
    missing=any(row['missing_metrics'] for row in channels)
    return {'status':'empty' if all(row['status']=='empty' for row in channels) else 'partial' if missing else 'ok',
        'records':len(channels),'channels':channels,'report_path':str(path),
        'terminal_requests_complete':True,'terminal_metrics_complete':not missing,
        'all_channels_source_complete':False,
        'limitation':'全部、APP、PC、微信、手Q、M为官方独立终端概况，不是全渠道来源明细；不相加UV、不用全部减APP推导来源。空表与缺失保持原样。'}


def latest(folder):
    paths=sorted(Path(folder).glob('*/report.json'),reverse=True)
    if not paths:raise FileNotFoundError('缺少指定日期的已保存证据')
    return paths[0]


def product_metric_coverage(rows,previous=None,*,derived=None):
    from .product_test import FIELDS
    result={}
    for field in FIELDS:
        known=sum(r.get(field) is not None for r in rows.values())
        zeros=sum(field in (derived or {}).get(i,{}) for i,r in rows.items() if r.get(field) is not None)
        item={'records':len(rows),'known_products':known,'missing_products':len(rows)-known,
            'raw_known_products':known-zeros,'derived_zero_products':zeros}
        if previous is not None:
            item.update(union_products=len(set(rows)|set(previous)),
                comparable_products=sum(rows[i].get(field) is not None and previous[i].get(field) is not None for i in set(rows)&set(previous)))
        result[field]=item
    return result


def collect(day,store,*,root=None):
    from .cli import capabilities
    from .product_test import load_day
    from .new_product_review import load_verified,AMOUNT
    if not re.fullmatch(r'jd:mall:\d+',store or ''):raise ValueError('全景必须绑定精确京东店铺')
    date.fromisoformat(day);root=Path(root) if root is not None else ROOT
    base=root/'data/jd'/store.replace(':','_')/day;started=time.monotonic();domains=[]
    def check(domain,command,loader,args=()):
        row={'domain':domain,'command':command,'scope':'saved_evidence_only'}
        try:
            detail=loader();row.update({'status':'empty' if detail.get('records')==0 else 'ok',**detail})
        except FileNotFoundError as error:row.update(status='missing',detail=str(error))
        except (OSError,ValueError,KeyError,TypeError) as error:row.update(status='invalid',detail=str(error))
        if row['status'] in ('missing','invalid'):row['next_call']={'platform':'jd','store':store,'command':command,'args':['--date',day,*args]}
        domains.append(row)
    def overview_data():
        path=base/'report.json';r=load_overview(path,day,store)
        return {'status':r['data_status'],'analysis_ready':r['analysis_ready'],'missing_core_metrics':r['missing_core_metrics'],
            'records':1,'metrics':r['metrics'][:10],'report_path':str(path),'limitation':'京东成交金额口径；不改称净销售额；'+r['availability_note']}
    def products():
        candidates=[p for d in (day,(date.fromisoformat(day)+timedelta(days=1)).isoformat()) for p in (root/'data/jd'/store.replace(':','_')/d/'products-spu-api').glob('*/products-spu-exports/report.json')]
        if not candidates:raise FileNotFoundError('缺少指定日期可用的SPU导出配对证据')
        rows,proof=load_day(day,store,root=root)
        ordered=sorted(rows.items(),key=lambda pair:-(pair[1]['amount'] or 0))
        previous=None;comparison_error=None
        try:previous,_=load_day((date.fromisoformat(day)-timedelta(days=1)).isoformat(),store,root=root)
        except (ValueError,KeyError,OSError) as error:comparison_error=str(error)
        coverage=product_metric_coverage(rows,previous,derived=proof.get('derived_zero_evidence'))
        comparison_pending=({'platform':'jd','store':store,'command':'product-full',
            'args':['--date',(date.fromisoformat(day)-timedelta(days=1)).isoformat(),'--dimension','spu']} if comparison_error else None)
        return {'status':'partial' if comparison_error or any(r['missing_products'] for r in coverage.values()) else 'ok',
            **({'next_call':comparison_pending} if comparison_pending else {}),
            'records':len(rows),'metric_coverage':coverage,'comparison_error':comparison_error,
            'derived_zero_cells':sum(len(fields) for fields in proof.get('derived_zero_evidence',{}).values()),
            'sample':[{'spu_id':i,**{k:r[k] for k in ('name','item_num','uv','buyers','amount')}} for i,r in ordered[:3]],
            'evidence':{k:v for k,v in proof.items() if k!='derived_zero_evidence'},'limitation':'官方有数据SPU，不等于所有在架商品；缺失不补零，严格推导零值另存原文证据；指标可比子集分别计数'}
    def new_products(dimension):
        path=latest(base/('new-products-'+dimension));r=load_verified(path,day,store,dimension=dimension)
        return {'records':len(r['rows']),'unique_products':len({x['id'] for x in r['rows']}),'sample':[{'id':x['id'],'flags':x['flags'],'成交金额':x['metrics'].get(AMOUNT)} for x in r['rows'][:3]],'report_path':str(path),'limitation':'官方打标新品，不等于首次上架年龄队列；列表流量/加购口径未核验，测款使用官方商品导出'}
    def traffic():
        path=latest(base/'traffic-tree');r=load_traffic(path,day,store,root=root)
        return {'records':len(r['nodes']),'app_complete':r['app_complete'],'all_channels_complete':False,'levels':r['levels'],'sample':[n for n in r['nodes'] if n['level']==1],'report_path':str(path),'limitation':'APP末次场域四层当日有数据分支；父子节点不相加，不代表全渠道'}
    check('overview','shop-overview',overview_data)
    check('products-spu','product-full',products,('--dimension','spu'))
    check('traffic-app','traffic-tree',traffic)
    check('traffic-terminals','traffic-channels',lambda:load_terminals(latest(base/'traffic-channels'),day,store))
    for dimension in ('sku','spu'):check('new-products-'+dimension,'new-products-'+dimension,lambda d=dimension:new_products(d))
    scope=capabilities()['data_scope']
    for domain,key in [('non-app-traffic','non_app_sources'),('advertising','advertising'),('customer-service','customer_service')]:
        domains.append({'domain':domain,'status':scope[key]['status'],'detail':scope[key]['reason']})
    def refund_data():
        from .refund_review import saved_context
        r=saved_context(day,store,root=root)
        return {'status':'partial','records':len(r['trend']),'metrics':r['metrics'],'missing_sources':r['missing_sources'],
            'limitation':'商智退款事件及服务单证据按指定日期复核；完整付款批次及父兄弟关系缺失时，不生成真实退货率'}
    check('refund-attribution','refund-review',refund_data)
    covered={d['command'] for d in domains if d.get('status') in ('ok','empty','partial')}
    catalog=[{'command':command,'status':'executed' if command=='panorama' else 'evidence_verified' if command in covered else 'not_run','evidence_domains':[d['domain'] for d in domains if d.get('command')==command and d['status'] in ('ok','empty','partial')],'note':'本次复核已保存原文，不表示本次在线采集成功；指标完整性见各数据域状态' if command in covered else '本次运行的全景核查' if command=='panorama' else '仅登记；本次未执行此命令'} for command in capabilities()['commands']]
    report={'platform':'jd','store_key':store,'date':day,'module':'标准全景报表','status':'partial','acquisition':'saved_evidence_revalidated','elapsed_seconds':round(time.monotonic()-started,3),'all_channels_complete':False,'coverage':dict(Counter(d['status'] for d in domains)),'domains':domains,'command_coverage':catalog,'notes':['仅复核指定日和指定店铺的现存证据；不借用其他日期，不自动发起补数','成功/空表/缺失/无效/未接入分别记录；invalid不能作为已知业务数据','首次上架日期和收藏仍有缺口；不宣称七模块全部完成']}
    report['data_scope']=scope
    report['registered_domains']=['overview','products-spu','traffic-app','traffic-terminals','new-products-sku','new-products-spu']
    report['registered_evidence_complete']=all(d['status'] in ('ok','partial','empty') for d in domains if d['domain'] in report['registered_domains'])
    report['notes'].append('registered_evidence_complete仅表示六个已接入域的原始证据均已核验；官方空表和缺失指标保留，不代表全指标、全渠道或全部业务已完成。')
    folder=base/'panorama'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');folder.mkdir(parents=True,exist_ok=False)
    report.update(report_path=str(folder/'report.json'),markdown_path=str(folder/'report.md'))
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    lines=['# 京东商智 · 已保存证据全景',f'店铺：{store}；统计日：{day}；状态：partial。','本次只复核已有证据，没有重新在线取数。','| 数据域 | 状态 | 记录数 | 范围或缺口 |','|---|---|---:|---|']
    for row in domains:lines.append('|'+ '|'.join(str(row.get(k,'—')).replace('|','／') for k in ('domain','status','records','limitation' if 'limitation' in row else 'detail'))+'|')
    terminal=next(row for row in domains if row['domain']=='traffic-terminals')
    if terminal['status'] in ('ok','partial','empty'):
        lines+=['','## 六终端概况','全部为官方独立汇总；终端访客不求和，空表与缺失不补零。',
            '| 终端 | 状态 | 店铺访客 | 成交金额 | 缺失指标 |','|---|---|---:|---:|---|']
        for channel in terminal['channels']:
            values=[channel['metrics'].get(name,{}).get('value') for name in ('店铺访客数','成交金额')]
            lines.append('| '+' | '.join([channel['name'],channel['status'],*['缺失' if value is None else str(value) for value in values],
                '、'.join(channel['missing_metrics']) or ('空表' if channel['status']=='empty' else '无')])+' |')
    product=next(row for row in domains if row['domain']=='products-spu')
    if product.get('metric_coverage'):
        lines+=['','## 商品指标覆盖','逐指标已知数与前日可比数，不能相互替代；仅代表官方有数据商品。',
            '|指标|当日记录|原始已知|推导零值|缺失|两日可比|两日集合|','|---|---:|---:|---:|---:|---:|---:|']
        for field,coverage in product['metric_coverage'].items():
            lines.append('|'+field+'|'+'|'.join(str(coverage.get(k,'未取得')) for k in ('records','raw_known_products','derived_zero_products','missing_products','comparable_products','union_products'))+'|')
    lines+=['','## 口径',*['- '+note for note in report['notes']],'','缺失域的补数命令和样例见同目录report.json。']
    (folder/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    return report
