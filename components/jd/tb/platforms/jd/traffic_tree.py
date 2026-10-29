"""Enumerate the official APP source hierarchy; completeness never implies all channels."""
from collections import Counter,deque
from datetime import date,datetime,timedelta,timezone
from pathlib import Path
import hashlib,json,re,sys
from .api_client import APIClient,ROOT
from .api_products import write_json
from .traffic_contract import FIELDS
from .overview import numeric,formatted

def index_dictionary(payload):
    if payload.get('header',{}).get('code')!=0 or payload.get('errors'):raise ValueError('来源字典业务状态失败')
    roots=payload.get('body',{}).get('data')
    if not isinstance(roots,list) or not roots:raise ValueError('缺少官方来源字典')
    index={}
    def walk(nodes,parents):
        if not isinstance(nodes,list) or len(parents)>=4:raise ValueError('字典层级不符合官方四层合同')
        for node in nodes:
            identifier=node.get('value');name=node.get('name');children=node.get('child') or []
            if not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9_]{1,32}',identifier) or not isinstance(name,str) or not name:raise ValueError('字典编号或名称无效')
            path=(*parents,identifier)
            if path in index:raise ValueError('字典父级内编号重复')
            index[path]={'name':name,'has_children':bool(children)}
            if children:walk(children,path)
    walk(roots,())
    return index

def collect(day,store,*,client=None,max_requests=100,root=None,persist=True):
    date.fromisoformat(day)
    if client is None:
        with APIClient({'platform':'jd','store_key':store},min_extension='0.8.3') as active:return collect(day,store,client=active,max_requests=max_requests,root=root,persist=persist)
    folder=(Path(root) if root is not None else ROOT)/'data/jd'/store.replace(':','_')/day/'traffic-tree'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    if persist:folder.mkdir(parents=True,exist_ok=False)
    errors=[];unknown=[];nodes=[];proofs=[];dictionary={};identity=None
    def query(key,scope=None):
        nonlocal identity
        payload,proof=client.request(key,day,**({'scope':scope} if scope else {}))
        identity=proof['identity']
        if identity.get('platform')!='jd' or identity.get('store_key')!=store:raise ValueError('来源响应店铺不符')
        raw=client.last_response_text
        if not isinstance(raw,str) or hashlib.sha256(raw.encode()).hexdigest()!=proof.get('response_sha256'):raise ValueError('来源正文与证据哈希不符')
        name='dictionary' if key=='source-dictionary' else 'page-'+str(len(proofs)+1).zfill(4)
        if persist:(folder/(name+'.json')).write_text(raw,encoding='utf-8')
        proofs.append({**proof,'scope':scope,'response_path':str(folder/(name+'.json')) if persist else proof.get('response_path')})
        return payload
    try:
        dictionary=index_dictionary(query('source-dictionary'))
        queue=deque([()]);queries=0
        while queue:
            parents=queue.popleft();level=len(parents)+1;seen=set();page=1;expected=None
            try:
                while True:
                    if queries>=max_requests:raise ValueError('达到本轮100页采集上限，不能标记完整')
                    scope={'level':level,'parents':list(parents),'page':page};queries+=1
                    payload=query('traffic-tree',scope)
                    if payload.get('header',{}).get('code')!=0 or payload.get('errors'):raise ValueError('来源业务状态失败')
                    body=payload.get('body') or {};rows=body.get('data');size=body.get('size')
                    if not isinstance(rows,list) or type(size) is not int or size<0 or size>100000:raise ValueError('来源数组或官方总行数无效')
                    if expected is None:expected=size
                    elif expected!=size:raise ValueError('分页期间官方总行数变化')
                    if len(rows)>100 or (not rows and len(seen)<expected):raise ValueError('来源分页缺失或超过登记页大小')
                    field='jdr_sch_traffic_cha_last_field_src_rmad_sz_'+str(level)
                    for row in rows:
                        identifier=row.get(field) if isinstance(row,dict) else None
                        if not isinstance(identifier,str) or not re.fullmatch(r'[A-Za-z0-9_]{1,32}',identifier) or identifier in seen:raise ValueError('分页编号缺失或重复，分页可能未生效')
                        seen.add(identifier);path=(*parents,identifier);entry=dictionary.get(path)
                        if entry is None:unknown.append(list(path))
                        node={'path':list(path),'parent_path':list(parents),'level':level,'id':identifier,
                          'name':entry['name'] if entry else None,'leaf':not entry['has_children'] if entry else None,
                          'metrics':{name:{'field':code,'unit':unit,'value':numeric(row.get(code)),'previous':numeric(row.get(code+'##compareValue')),
                            'relative_change':numeric(row.get(code+'##compare'))} for name,code,unit in FIELDS}}
                        nodes.append(node)
                        if entry and entry['has_children']:queue.append(path)
                    if len(seen)>expected:raise ValueError('来源返回行数超过官方总行数')
                    if len(seen)==expected:break
                    page+=1
                print('APP来源已核对：'+('/'.join(parents) or '根层')+'；'+str(len(seen))+'条',file=sys.stderr,flush=True)
            except (ValueError,RuntimeError,OSError,TimeoutError) as error:
                errors.append(('/'.join(parents) or '根层')+'：'+str(error))
                if queries>=max_requests:break
    except (ValueError,RuntimeError,OSError,TimeoutError) as error:errors.append(str(error))
    report={'platform':'jd','store':identity or {'platform':'jd','store_key':store},'status':'partial','date':day,
      'compare_date':(date.fromisoformat(day)-timedelta(days=1)).isoformat(),'channel':'app','scope':'official_app_available_source_tree',
      'app_complete':not errors and not unknown,'all_channels_complete':False,'captured_pages':len(proofs)-1 if proofs else 0,
      'captured_nodes':len(nodes),'levels':dict(Counter(node['level'] for node in nodes)),'dictionary_nodes':len(dictionary),
      'unknown_paths':unknown,'errors':errors,'nodes':nodes,'requests':proofs,
      'notes':['当前范围为官方APP来源明细；非APP来源经用户确认不接入、不列为缺口；不混用归因口径',
        '完整仅指本次统计日、官方字典可展开分支及各分支分页均已取回；不是全渠道完整',
        '父子节点分开保留，不相加；来源UV不可相加当全店去重UV；空值不补0',
        '字典为当前读取版本，不代表历史标签定义始终相同'],
      'report_path':str(folder/'report.json'),'markdown_path':str(folder/'report.md')}
    if not persist:return report
    write_json(folder/'report.json',report)
    lines=['# 京东商智 · APP来源覆盖','',f"统计日：{day}；APP本次范围完整：{report['app_complete']}；全渠道完整：否。",'',*['- '+note for note in report['notes']],
      '','| 来源路径 | 层级 | 名称 | 引入成交金额 | 前一日 |','|---|---:|---|---:|---:|']
    for node in nodes:
        metric=node['metrics']['引入成交金额'];name=(node['name'] or '未知').replace('|','／')
        lines.append('| '+' / '.join(node['path'])+' | '+str(node['level'])+' | '+name+' | '+formatted(metric['value'],'元')+' | '+formatted(metric['previous'],'元')+' |')
    lines+=['','## 尚未覆盖',*['- '+error for error in errors],*['- 未知字典路径：'+'/'.join(path) for path in unknown],'- 范围外：非APP来源明细，不作为待补数据。','',report['report_path']]
    (folder/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    return {**{key:value for key,value in report.items() if key not in ('nodes','requests')},'preview':nodes[:5]}
