"""Local report jobs: short MCP start/status calls and fixed read-only collectors."""
from datetime import date,datetime,timezone
from pathlib import Path
import argparse,json,os,re,subprocess,sys,uuid
from ...core.bridge import BridgeLock
from .api_products import ROOT,write_json

def folder():return ROOT/'.runtime/report-jobs'
COMMANDS=('daily-check','weekly-review','traffic-tree','new-products-sku','new-products-spu','order-list','after-sales-list','refund-enrich','product-diagnosis','product-test')

def binding(command,product_id):
    if command=='product-diagnosis':
        if not re.fullmatch(r'[1-9][0-9]{0,15}',str(product_id or '')):raise ValueError('SKU诊断必须绑定商品编号')
    elif product_id is not None:raise ValueError('该任务不接受商品编号')

def read(job_id,day,store,command='weekly-review',product_id=None,weeks=1):
    binding(command,product_id)
    if command not in COMMANDS:raise ValueError('未登记的后台任务')
    if not re.fullmatch(r'[0-9a-f]{32}',job_id or '') or not re.fullmatch(r'jd:mall:\d+',store or ''):raise ValueError('无效的任务或店铺编号')
    date.fromisoformat(day)
    record=json.loads((folder()/(job_id+'.json')).read_text(encoding='utf-8'))
    if record.get('date')!=day or record.get('store_key')!=store or record.get('command')!=command:raise ValueError('任务店铺、日期或命令不符')
    if record.get('product_id')!=product_id:raise ValueError('任务商品编号不符')
    if weeks not in (1,2) or (command!='product-test' and weeks!=1) or record.get('weeks',1)!=weeks:raise ValueError('任务观察周数不符')
    return record

def status(job_id,day,store,command='weekly-review',product_id=None,weeks=1):
    record=read(job_id,day,store,command,product_id,weeks)
    log=folder()/(job_id+'.log')
    if log.exists():
        with log.open('rb') as stream:
            stream.seek(max(0,log.stat().st_size-3000));text=stream.read().decode('utf-8','replace')
        record['progress']=text.splitlines()[-6:]
        record['progress_updated_at']=datetime.fromtimestamp(log.stat().st_mtime,timezone.utc).isoformat()
    if record['status'] in ('queued','running'):
        record['next_call']={'command':command,'args':['--date',day,'--job-id',job_id],'store':store,'platform':'jd'}
        if product_id:record['next_call']['args']+=['--product-id',product_id]
        if command=='product-test':record['next_call']['args']+=['--weeks',str(weeks)]
    return record

def start(day,store,command='weekly-review',product_id=None,weeks=1):
    binding(command,product_id)
    if command not in COMMANDS:raise ValueError('未登记的后台任务')
    if weeks not in (1,2) or (command!='product-test' and weeks!=1):raise ValueError('任务观察周数不符')
    if not re.fullmatch(r'jd:mall:\d+',store or ''):raise ValueError('任务必须绑定精确京东店铺')
    date.fromisoformat(day);folder().mkdir(parents=True,exist_ok=True)
    lock=BridgeLock(folder()/'launch.lock');lock.acquire(wait=3)
    try:
        suffix='' if command=='weekly-review' else '_'+command
        if product_id:suffix+='_'+product_id
        if command=='product-test':suffix+='_weeks'+str(weeks)
        active=folder()/(store.replace(':','_')+'_'+day+suffix+'.active')
        if active.exists():
            prior=read(active.read_text(encoding='ascii').strip(),day,store,command,product_id,weeks)
            if prior['status'] in ('queued','running'):return status(prior['job_id'],day,store,command,product_id,weeks)
        job_id=uuid.uuid4().hex
        record={'job_id':job_id,'status':'queued','platform':'jd','store_key':store,'date':day,'command':command,
          'started_at':datetime.now(timezone.utc).isoformat()}
        if product_id:record['product_id']=product_id
        if command=='product-test':record['weeks']=weeks
        write_json(folder()/(job_id+'.json'),record);active.write_text(job_id,encoding='ascii')
        kwargs={'cwd':str(ROOT),'stdin':subprocess.DEVNULL,'env':{**os.environ,'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8'}}
        if os.name=='nt':kwargs['creationflags']=subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP
        else:kwargs['start_new_session']=True
        try:
            with (folder()/(job_id+'.log')).open('ab') as log:
                argv=[sys.executable,'-m','tb.platforms.jd.report_jobs','--command',command,'--job-id',job_id,'--date',day,'--store',store]
                if product_id:argv+=['--product-id',product_id]
                if command=='product-test':argv+=['--weeks',str(weeks)]
                subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,**kwargs)
        except Exception:
            write_json(folder()/(job_id+'.json'),{**record,'status':'failed','error':'后台进程未启动'});raise
        return status(job_id,day,store,command,product_id,weeks)
    finally:lock.release()

def work(job_id,day,store,command='weekly-review',product_id=None,weeks=1):
    record=read(job_id,day,store,command,product_id,weeks)
    if record['status']!='queued':raise ValueError('任务已领取或结束，不重复执行')
    from .power import SystemAwake
    awake=SystemAwake();power_state=awake.__enter__()
    try:
        write_json(folder()/(job_id+'.json'),{**record,'status':'running','pid':os.getpid(),'system_awake':power_state})
        if command in ('daily-check','weekly-review'):
            if command=='weekly-review':from .weekly import collect
            else:from .daily import collect
            from .business_structure import tool_summary
            report=tool_summary(collect(day,store))
        elif command=='product-test':
            from .product_test import collect
            report=collect(day,store,weeks=weeks)
        elif command=='product-diagnosis':
            from .product_diagnosis import collect
            report=collect(day,store,product_id)
        elif command=='order-list':
            from .orders import collect
            report=collect(day,store,all_pages=True)
        elif command=='after-sales-list':
            from .after_sales import collect_all
            report=collect_all(day,store)
        elif command=='refund-enrich':
            from .refund_enrichment import collect
            report=collect(day,store)
        elif command.startswith('new-products-'):
            from .new_products import collect
            report=collect(day,store,command.rsplit('-',1)[1])
        else:
            from .traffic_tree import collect
            report=collect(day,store)
        result={**record,'status':'complete','data_status':report.get('status','unknown'),'finished_at':datetime.now(timezone.utc).isoformat(),'report':report}
    except Exception as error:
        result={**record,'status':'failed','finished_at':datetime.now(timezone.utc).isoformat(),'error':str(error)}
    finally:awake.__exit__(None,None,None)
    result['system_awake']=power_state
    write_json(folder()/(job_id+'.json'),result)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--job-id',required=True);parser.add_argument('--date',required=True);parser.add_argument('--store',required=True);parser.add_argument('--command',choices=COMMANDS,default='weekly-review')
    parser.add_argument('--product-id')
    parser.add_argument('--weeks',type=int,choices=[1,2],default=1)
    args=parser.parse_args();work(args.job_id,args.date,args.store,args.command,args.product_id,args.weeks)
