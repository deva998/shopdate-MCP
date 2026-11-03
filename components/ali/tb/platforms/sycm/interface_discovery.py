"""Bounded official source discovery. All online reads use the existing MCP bridge."""
import hashlib,json,re,time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin,urlsplit

PAGES={'traffic-board':'https://sycm.taobao.com/flow/monitor/overview','shop-source':'https://sycm.taobao.com/flow/monitor/shopsource/construction'}
WRITE=re.compile(r'(^|[/.])(add|create|update|delete|remove|save|submit|cancel|set|edit|upload|apply|bind|unbind)([/.]|$)',re.I)

def validate_asset(url):
 u=urlsplit(url)
 if u.scheme!='https' or u.netloc!='g.alicdn.com' or u.query or u.fragment or '%' in u.path or '..' in u.path or not re.fullmatch(r'/dt/(?:sycm-[A-Za-z0-9_-]+|ops-flow)/[A-Za-z0-9_./-]+\.js',u.path):raise ValueError('Only observed public SYCM JavaScript assets without credentials/query are supported')
 return url

def validate_page(name):
 if name not in PAGES:raise ValueError('Only traffic-board or shop-source pages are supported')
 return PAGES[name]

def parse_source(text,url):
 class Parser(HTMLParser):
  def __init__(self):super().__init__();self.scripts=[]
  def handle_starttag(self,tag,attrs):
   if tag=='script':
    src=dict(attrs).get('src')
    if src:
     u=urlsplit(urljoin(url,src))
     if u.scheme=='https' and not u.username and not u.password:self.scripts.append(u._replace(query='',fragment='').geturl())
 p=Parser();p.feed(text)
 paths=sorted({x for x in re.findall(r'[\"\x27`]((?:/flow/|/portal/|/cc/)[A-Za-z0-9_./-]+\.json)[\"\x27`]',text) if not WRITE.search(x)})
 static_refs=sorted(set(re.findall(r'(?:https:)?//g\.alicdn\.com/[A-Za-z0-9_./-]+(?:\.js|\.html|\.json)',text)))
 bootstrap_paths=sorted(set(re.findall(r'[\"\x27`](/[A-Za-z0-9_./-]+\.json)[\"\x27`]',text)))
 bootstrap_static=sorted(set(re.findall(r'(?:https:)?//g\.alicdn\.com/[A-Za-z0-9_./-]+',text)))
 inline_keys=sorted(set(re.findall(r'(?:window\.)?([A-Za-z_$][\w$.]{1,80})\s*=',text))) if not url.endswith('.js') else []
 versions=re.findall(r'ctxSFlowVersion\s*=\s*[\"\x27]?([0-9]+(?:\.[0-9]+)+)',text)
 versions+=re.findall(r'name=[\"\x27]ctxSFlowVersion[\"\x27][^>]*content=[\"\x27]([0-9.]+)[\"\x27]',text)
 derived=[f'https://g.alicdn.com/dt/ops-flow/{v}/{name}.js' for v in sorted(set(versions)) for name in ('app','vendors')]
 chunks=[];base=re.search(r'\w+\.p=[\"\x27](//g\.alicdn\.com/dt/ops-flow/[0-9.]+/)[\"\x27]',text)
 names=re.search(r's\.src=function\(e\).*?\(\{(.*?)\}\[e\]\|\|e\)\+[\"\x27]\.js',text)
 if base and names:
  mapping=dict(re.findall(r'(\d+):[\"\x27]([A-Za-z0-9_-]+)[\"\x27]',names.group(1)))
  chunks=['https:'+base.group(1)+mapping.get(i,i)+'.js' for i in sorted(set(mapping)|set(re.findall(r'\b\w+\.e\((\d+)\)',text)),key=int)]
 return {'source_url':url,'sha256':hashlib.sha256(text.encode()).hexdigest(),'characters':len(text),'scripts':list(dict.fromkeys(p.scripts)),'candidate_paths':paths,'static_references':static_refs,'bootstrap_static_urls':bootstrap_static,'flow_versions':versions,'derived_flow_assets':derived,'chunk_asset_references':chunks,'derivation':'Official micro-v2 resource template and ops-flow webpack runtime references; never executed','bootstrap_paths':bootstrap_paths,'status':'candidates_not_verified'}

def collect(args):
 from .cli import load_taobao_cookies
 from ...core import transport
 from ...core.errors import TbError
 url=validate_page(args.page);cookies=load_taobao_cookies();client=cookies.client
 if not getattr(client,'_bridge_server',None):raise TbError('Discovery requires the extension-backed MCP transport')
 try:
  if args.asset_url:
   asset=validate_asset(args.asset_url)
   if not args.evidence:raise ValueError('--asset-url requires --evidence from previous discovery')
   evidence=json.loads(Path(args.evidence).read_text(encoding='utf8'))
   if asset not in evidence.get('scripts',[])+evidence.get('asset_references',[])+evidence.get('derived_flow_assets',[])+evidence.get('chunk_asset_references',[]):raise ValueError('Asset was not observed in source evidence')
   from ...core.bridge import version_tuple
   if version_tuple(client._bridge_server.extension_version)<version_tuple('0.9.43'):raise TbError('Public asset discovery needs bridge 0.9.43; refresh shopdate-cli extension once')
   result=client._bridge_server.submit({'url':asset,'public_asset':True},60)
   if result.get('error'):raise TbError(str(result['error']))
   from types import SimpleNamespace
   response=SimpleNamespace(status_code=result.get('status'),text=result.get('text',''),url=asset);url=asset
  else:
   client._guard();response=client.session.get(url,timeout=60)
  if response.status_code!=200:raise TbError('Official page returned HTTP '+str(response.status_code))
  text=response.text
  if any(s in text for s in ['请完成安全验证','验证码','滑块验证']):raise TbError('Security verification required; stop and ask user to complete it')
  if 'login' in (response.url or '').lower():raise TbError('Login expired; stop')
  if len(text)>5000000:raise TbError('Source exceeds bounded discovery limit')
  result=parse_source(text,url);result['transport']='shopdate_symc_MCP_extension';result['observed_at']=time.strftime('%Y-%m-%dT%H:%M:%S%z')
  refs=[]
  for link in re.findall(r'(?:https:)?//g\.alicdn\.com/[A-Za-z0-9_./-]+\.js',text):
   try:refs.append(validate_asset('https:'+link if link.startswith('//') else link))
   except ValueError:pass
  result['asset_references']=sorted(set(refs))
  result['scope']='Official page references only; no guessed endpoints or script execution'
  if not result['scripts'] and not result['candidate_paths']:result['status']='no_interface_evidence'
  if args.out:
   p=Path(args.out);p.parent.mkdir(parents=True,exist_ok=True)
   if args.asset_url:
    public=p.with_suffix('.public-source.js');public.write_text(text,encoding='utf8');result['public_source_file']=str(public)
   p.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
  print(json.dumps(result,ensure_ascii=False,indent=2))
 finally:transport.release(client)

def register(sp):
 from . import traffic
 traffic.register(sp)
 p=sp.add_parser('interface-discover',help='通过MCP只读数据桥发现官方流量页面引用和接口声明，不执行页面脚本')
 p.add_argument('--page',choices=tuple(PAGES),required=True);p.add_argument('--asset-url');p.add_argument('--evidence');p.add_argument('--out');p.set_defaults(func=collect)
