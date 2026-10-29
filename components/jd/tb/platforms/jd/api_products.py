"""Create exact official exports, track new task IDs, download, reconcile, and report."""
from datetime import date,datetime,timedelta,timezone
import hashlib,json,re,sys,time,uuid
from pathlib import Path
from decimal import Decimal
from .api_client import APIClient,ROOT,make_job
from .api_exports import find_new_task,download_xlsx
from .product_downloads import export_prefix
from .product_exports import load_export,save_comparison,ExportReader
from . import overview,reports


def write_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:temp.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8');temp.replace(path)
    finally:
        if temp.exists():temp.unlink()


def cached_export(state,day,store,dimension,contract_hash,control,*,export_loader=None):
    expected={'store':store,'date':day,'dimension':dimension,'request_sha256':contract_hash,'state':'complete'}
    if any(state.get(key)!=value for key,value in expected.items()):raise ValueError('缓存店铺、日期、维度或请求合同不符')
    download=state.get('download') or {};source_identity=download.get('request',{}).get('identity',{})
    if source_identity.get('platform')!='jd' or source_identity.get('store_key')!=store:raise ValueError('缓存来源身份不符')
    path=Path(download.get('path',''))
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=download.get('sha256'):raise ValueError('缓存文件缺失或哈希不符')
    parsed=(export_loader or load_export)(path,day,dimension,store)
    if control.get('store',{}).get('store_key')!=store:raise ValueError('缓存概况店铺不符')
    slot='value' if day==control.get('date') else 'previous' if day==control.get('compare_date') else None
    if not slot:raise ValueError('缓存概况日期不符')
    metrics={item['name']:item for item in control['metrics']}
    for name,tolerance in [('成交金额',Decimal('.01')),('成交商品件数',Decimal(0))]:
        value=metrics.get(name,{}).get(slot)
        if value is None or abs(Decimal(str(parsed['summary']['metrics'][name]))-Decimal(str(value)))>tolerance:
            raise ValueError('缓存与最新概况不符：'+name)
    return path,{**download,'retrieval':'verified_local_cache','revalidated_at':datetime.now(timezone.utc).isoformat(),
      'latest_control_request':control.get('query_proof',{}).get('request_started_at')}


def collect(day,store,dimension,*,client=None,reuse_verified=False):
    export_prefix(store,day)
    if dimension not in ('spu','sku'):raise ValueError('导出维度无效')
    previous=(date.fromisoformat(day)-timedelta(days=1)).isoformat()
    identity={'platform':'jd','store_key':store}
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder=ROOT/'data/jd'/store.replace(':','_')/day/('products-'+dimension+'-api')/run_id
    folder.mkdir(parents=True,exist_ok=False)
    owner=client is None;client=client if client is not None else APIClient(identity)
    paths=[];tasks=[];reader=ExportReader(loader=load_export)
    try:
        if owner:client.__enter__()
        payload,proof=client.request('overview',day)
        request=overview.make_request(reports.contracts()['overview']['template'],day)
        control=overview.summarize(payload,request,'registered-api',proof['request_started_at'])
        control.update(platform='jd',store=proof['identity'],query_proof=proof)
        control_path=folder/'overview.json';write_json(control_path,control)
        for selected in (day,previous):
            prefix=export_prefix(store,selected)
            checkpoint=ROOT/'.runtime/api-export-jobs'/store.replace(':','_')/selected/(dimension+'.json')
            body=make_job('export-submit',selected,identity,dimension=dimension)['body']
            contract_hash=hashlib.sha256(body.encode()).hexdigest()
            state=json.loads(checkpoint.read_text(encoding='utf-8')) if checkpoint.exists() else None
            if reuse_verified and state is not None and state.get('state')=='complete':
                try:cached=cached_export(state,selected,store,dimension,contract_hash,control,export_loader=reader)
                except (ValueError,OSError):
                    print('缓存未通过最新校验，重新导出：'+selected,file=sys.stderr,flush=True)
                else:
                    path,evidence=cached;paths.append(path);tasks.append(evidence)
                    print('复用已重新校验的官方文件：'+selected,file=sys.stderr,flush=True)
                    continue
            pending=state is not None and state.get('state')!='complete'
            if pending:
                if any(state.get(k)!=v for k,v in {'store':store,'date':selected,'dimension':dimension,'request_sha256':contract_hash}.items()):raise ValueError('未完成任务与当前合同不同；停止，未重复提交')
                print('恢复未完成导出：'+selected+'；不重复提交',file=sys.stderr,flush=True)
            else:
                baseline,_=client.request('task-list',selected)
                rows=baseline.get('body',{}).get('data')
                if not isinstance(rows,list):raise ValueError('缺少任务基线列表')
                state={'store':store,'date':selected,'dimension':dimension,'request_sha256':contract_hash,'state':'submission_pending',
                  'baseline_ids':[str(r['taskId']) for r in rows if isinstance(r,dict) and 'taskId' in r],
                  'issued_at':datetime.now(timezone.utc).isoformat(timespec='milliseconds'),'task_id':None}
                write_json(checkpoint,state)
                # Checkpoint precedes the only submit. Unknown completion is resumed via list, never re-POSTed.
                submitted,submission_proof=client.request('export-submit',selected,dimension=dimension)
                state.update(state='submitted',submission_proof=submission_proof)
                data=submitted.get('body',{}).get('data')
                if isinstance(data,list) and len(data)==1 and isinstance(data[0],dict):
                    identifier=str(data[0].get('taskId',''))
                    if re.fullmatch(r'\d{16,24}',identifier):state['task_id']=identifier
                write_json(checkpoint,state)
            deadline=time.monotonic()+120;task=None
            while time.monotonic()<deadline:
                payload,_=client.request('task-list',selected)
                task=find_new_task(payload.get('body',{}).get('data'),state['baseline_ids'],prefix,state['issued_at'],task_id=state.get('task_id'))
                if task:
                    state.update(state='generating',task_id=task['taskId'],task=task);write_json(checkpoint,state)
                    if task['taskStatues']==2:break
                time.sleep(2)
            else:raise ValueError('新导出尚未完成；下次恢复任务，不重复提交。记录：'+str(checkpoint))
            payload,file_proof=client.request('task-file',selected,task=task)
            links=payload.get('body',{}).get('data')
            if not isinstance(links,list) or len(links)!=1 or not isinstance(links[0],dict) or not isinstance(links[0].get('fileUrl'),str):raise ValueError('新任务没有唯一官方下载地址')
            path=folder/(prefix+'_'+task['taskId']+'.xlsx')
            downloaded=download_xlsx(links[0]['fileUrl'],path)
            parsed=reader(path,selected,dimension,store)
            evidence={**downloaded,'task_id':task['taskId'],'task_created_at':task['createTime'],'date':selected,
              'rows':len(parsed['items']),'request':file_proof,'resumed':pending,'checkpoint':str(checkpoint),
              'retrieval':'resumed_export' if pending else 'fresh_export'}
            tasks.append(evidence);paths.append(path)
            # Complete only this day after download+schema+internal totals; final comparison remains separate.
            state.update(state='complete',download=evidence);write_json(checkpoint,state)
            print('官方导出已校验：'+selected+'；商品数'+str(len(parsed['items'])),file=sys.stderr,flush=True)
        comparison=save_comparison(paths[0],paths[1],control_path,day,dimension,store,export_loader=reader)
        comparison['processing']={'xlsx_parse_count':reader.parse_count,'parse_reuse_hits':reader.cache_hits,
            'scope':'same_command_only_hash_and_latest_totals_revalidated'}
        evidence={'status':'ok','acquisition':'registered_api_official_export','existing_tasks_only':all(item.get('retrieval')=='verified_local_cache' for item in tasks),'files':tasks,'requests':client.audit,
          'comparison':comparison,'notes':['按retrieval区分新建导出、恢复未完成任务及哈希/最新概况重新核验后的本地文件；不会把缓存说成新响应','官方有数据商品导出，不宣称覆盖所有在架商品','UV不可按商品相加当全店去重人数']}
        proof_path=folder/'acquisition.json';write_json(proof_path,evidence)
        comparison.update(acquisition='registered_api_official_export',acquisition_path=str(proof_path))
        comparison['reused_dates']=[item['date'] for item in tasks if item.get('retrieval')=='verified_local_cache']
        return comparison
    except Exception as error:
        write_json(folder/'failure.json',{'status':'failed','error':str(error),'requests':client.audit,'completed_files':tasks})
        raise
    finally:
        if owner:client.__exit__(None,None,None)
