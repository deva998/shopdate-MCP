"""Download an existing, exact-scope official export. Never submits export tasks."""
import hashlib,re,time,uuid,zipfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler,Request,build_opener
from .product_downloads import export_prefix


def find_new_task(rows,baseline,prefix,issued,*,task_id=None):
    if not isinstance(rows,list):raise ValueError('下载任务列表不是数组')
    start=datetime.fromisoformat(issued.replace('Z','+00:00'))
    if start.tzinfo is None:raise ValueError('任务提交时间必须带时区')
    local=start.astimezone(timezone(timedelta(hours=8))).replace(microsecond=0,tzinfo=None)
    matches=[]
    for row in rows:
        if not isinstance(row,dict) or row.get('taskName')!=prefix:continue
        identifier=str(row.get('taskId',''))
        if not re.fullmatch(r'\d{16,24}',identifier):raise ValueError('新任务ID无效')
        if identifier in baseline or (task_id and identifier!=task_id):continue
        try:created=datetime.strptime(row.get('createTime',''),'%Y-%m-%d %H:%M:%S')
        except (TypeError,ValueError):raise ValueError('新任务创建时间无效') from None
        if created<local:continue
        if type(row.get('taskStatues')) is not int or row['taskStatues'] not in (0,1,2):raise ValueError('新导出任务失败或状态未验证')
        matches.append({**row,'taskId':identifier})
    if len(matches)>1:raise ValueError('本次存在多个匹配新任务，停止避免错配')
    return matches[0] if matches else None


def choose_task(rows,store,day):
    prefix=export_prefix(store,day)
    if not isinstance(rows,list):raise ValueError('下载任务列表不是数组')
    matches=[]
    for row in rows:
        if not isinstance(row,dict) or row.get('taskName')!=prefix or type(row.get('taskStatues')) is not int or row['taskStatues']!=2:continue
        if not re.fullmatch(r'\d{16,24}',str(row.get('taskId',''))):raise ValueError('任务ID无效')
        try:created=datetime.strptime(row.get('createTime',''),'%Y-%m-%d %H:%M:%S')
        except (TypeError,ValueError):raise ValueError('任务创建时间无效') from None
        matches.append((created,row))
    if not matches:raise ValueError('没有指定店铺、日期已生成的官方导出；不会提交新任务或使用其他日期')
    newest=max(x[0] for x in matches);selected=[x[1] for x in matches if x[0]==newest]
    if len(selected)!=1:raise ValueError('多个同时间导出任务，停止避免错配')
    return {**selected[0],'taskId':str(selected[0]['taskId'])}


def validate_file_url(url):
    if not isinstance(url,str) or len(url)>16000 or any(ord(c)<33 for c in url):raise ValueError('下载地址无效')
    # The official API returns //storage.jd.com/...; the HTTPS page resolves it to HTTPS.
    if url.startswith('//'):url='https:'+url
    try:u=urlsplit(url);port=u.port
    except ValueError:raise ValueError('下载地址无效') from None
    host=(u.hostname or '').lower()
    if u.scheme!='https' or u.username or u.password or port not in (None,443) or u.fragment or not (host=='storage.360buyimg.com' or host.endswith('.jd.com')):
        raise ValueError('拒绝非官方HTTPS下载地址')
    return url


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        newurl=validate_file_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def download_xlsx(url,destination,*,open_url=None):
    url=validate_file_url(url)
    destination=Path(destination)
    if destination.suffix.lower()!='.xlsx' or destination.exists():raise ValueError('下载目标必须是未存在的XLSX文件')
    destination.parent.mkdir(parents=True,exist_ok=True)
    partial=destination.with_name(uuid.uuid4().hex+'.part')
    opener=open_url or build_opener(OfficialRedirect()).open
    size=0;digest=hashlib.sha256();deadline=time.monotonic()+90;owned=False
    try:
        with opener(Request(url,headers={'Accept':'application/octet-stream'}),timeout=30) as response,partial.open('xb') as output:
            owned=True
            if response.status!=200:raise ValueError('文件下载HTTP状态失败')
            validate_file_url(response.geturl())
            while True:
                chunk=response.read(256*1024)
                if not chunk:break
                size+=len(chunk)
                if size>100*1024*1024 or time.monotonic()>deadline:raise ValueError('文件超过下载大小或时间上限')
                output.write(chunk);digest.update(chunk)
        if not zipfile.is_zipfile(partial):raise ValueError('下载内容不是XLSX，可能是登录或错误页面')
        with zipfile.ZipFile(partial) as archive:
            if not {'[Content_Types].xml','xl/workbook.xml'}.issubset(archive.namelist()) or sum(x.file_size for x in archive.infolist())>512*1024*1024:
                raise ValueError('下载文件不是受限大小的Excel工作簿')
            if archive.testzip() is not None:raise ValueError('下载文件校验失败')
        partial.rename(destination)
        return {'path':str(destination.resolve()),'bytes':size,'sha256':digest.hexdigest()}
    except (ValueError,FileExistsError):raise
    except Exception as error:
        # Never echo a signed URL, credentials, or remote error body into logs.
        kind=type(error).__name__
        reason=getattr(error,'reason',None)
        if reason is not None:kind+='/'+type(reason).__name__
        code=getattr(error,'code',None)
        if isinstance(code,int):kind+=' HTTP '+str(code)
        raise ValueError('官方文件下载失败：'+kind+'；未保存为有效工作簿，未输出签名链接') from None
    finally:
        if owned and partial.exists():partial.unlink()
