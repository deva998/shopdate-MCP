"""Acquire official exports through native page controls and verify new local files."""
import json,shutil,time,zipfile
from datetime import date,datetime,timedelta,timezone
from pathlib import Path

def export_prefix(store,day):
    if not store.startswith('jd:mall:') or not store.removeprefix('jd:mall:').isdigit():raise ValueError('必须指定精确京东店铺')
    day=date.fromisoformat(day).isoformat()
    return store.removeprefix('jd:mall:')+'_商品明细_离线_不包括对比时间_汇总下载_'+day+'_'+day

def snapshot(folder):
    return {p.name:(p.stat().st_size,p.stat().st_mtime_ns) for p in Path(folder).glob('*.xlsx') if p.is_file()}

def find_new(folder,before,prefix):
    matches=[]
    for p in Path(folder).glob(prefix+'_*.xlsx'):
        try:
            info=(p.stat().st_size,p.stat().st_mtime_ns)
            if before.get(p.name)!=info and zipfile.is_zipfile(p):matches.append(p)
        except OSError:continue
    if len(matches)>1:raise ValueError('出现多个本次新导出文件，停止避免错配')
    return matches[0] if matches else None

def collect(day,store,dimension,downloads_dir=None):
    from . import reports,overview
    from .cli import capture,save_overview,ROOT
    from ...core.bridge import BridgeServer
    from .platform import JD
    from .product_exports import load_export,save_comparison
    # Native Chrome downloads remain in the user's configured folder; never move/delete originals.
    downloads=Path(downloads_dir or Path.home()/'Downloads')
    if not downloads.is_dir():raise ValueError('下载目录不存在，请指定 --downloads-dir')
    export_prefix(store,day)
    expected={'platform':'jd','store_key':store};key='products-'+dimension
    bridge=BridgeServer(JD);started=False;paths=[];evidence=[]
    try:
        bridge.start();started=True
        request=overview.make_request(reports.contracts()['overview']['template'],day)
        control,_=save_overview(capture(request,'overview',expected,bridge=bridge),request)
        for selected in [day,(date.fromisoformat(day)-timedelta(days=1)).isoformat()]:
            contract=reports.contracts()[key];body=overview.make_request(contract['template'],selected)
            before=snapshot(downloads);issued=datetime.now(timezone.utc).isoformat(timespec='milliseconds')
            job={'url':contract['endpoint'],'launch':contract['page'],'report_key':key,'method':'POST','body':json.dumps(body),
                 'operation':'official-export','transport':'background-native','expected_store':expected,'requested_after':issued,
                 'is_yesterday':selected==(datetime.now(timezone(timedelta(hours=8))).date()-timedelta(days=1)).isoformat()}
            result=bridge.submit(job,150)
            if result.get('error'):raise ValueError(result['error'])
            from ...core.stores import verify_identity
            verify_identity(expected,result.get('identity') or {})
            prefix=export_prefix(store,selected)
            if result.get('source')!='official-page-download' or result.get('prefix')!=prefix or not result.get('download_clicked'):raise ValueError('缺少本次官方导出证据')
            clicked=datetime.fromisoformat(result['download_clicked_at'].replace('Z','+00:00'))
            elapsed=(clicked-datetime.fromisoformat(issued)).total_seconds()
            if elapsed<0 or elapsed>150:raise ValueError('导出任务过期或响应时间无效')
            deadline=time.monotonic()+60;found=None
            while time.monotonic()<deadline:
                found=find_new(downloads,before,prefix)
                if found:break
                time.sleep(.3)
            if not found:raise ValueError('尚未收到本次完整XLSX文件；核对Chrome下载目录或下载提示，不会使用旧文件')
            load_export(found,selected,dimension,store)
            folder=ROOT/'data/jd'/store.replace(':','_')/selected/key/'official-export';folder.mkdir(parents=True,exist_ok=True)
            destination=folder/found.name;shutil.copy2(found,destination);paths.append(destination);evidence.append(result)
        compact=save_comparison(paths[0],paths[1],control['report_path'],day,dimension,store)
        proof=ROOT/'data/jd'/store.replace(':','_')/day/('products-'+dimension+'-exports')/'acquisition.json'
        proof.write_text(json.dumps({'source':'official-page-download','tasks':evidence},ensure_ascii=False,indent=2),encoding='utf-8')
        compact.update(acquisition='official-page-download',acquisition_path=str(proof))
        return compact
    finally:
        if started:bridge.stop()
        else:bridge.server_close()
