"""Bounded official source discovery. All online reads use the existing MCP bridge."""
import hashlib,json,re,time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin,urlsplit

PAGES={'traffic-board':'https://sycm.taobao.com/flow/monitor/overview','shop-source':'https://sycm.taobao.com/flow/monitor/shopsource/construction'}
PAGES.update({name:'https://sycm.taobao.com'+path for name,path in {
 'marketing-tools':'/xsite/promotion/promotion/sales',
 'trade-realtime':'/ipoll/index.htm','trade-sales':'/fa/trade/detail','trade-refunds':'/fa/refund/analysis',
 'product-macro':'/cc/macro_monitor','product-ranking':'/cc/item_rank','category-360':'/cc/new_cate_archives',
 'new-products':'/cc/new_item_analysis','product-relate':'/cc/item_relate','product-video':'/cc/video/analysis',
 'sales-overview':'/bda/tradinganaly/overview/overview.htm',
 'sales-structure':'/bda/tradinganaly/constitute/constitute.htm',
 'customer-overview':'/cc/customer/overview','customer-trip':'/cc/customer/trip',
 'customer-fans':'/cc/customer/fans','customer-member':'/cc/customer/member','customer-purchased':'/cc/customer/regular',
 'customer-focus':'/cc/customer/focus_analysis','customer-shop-pages':'/flow/page/overview_new',
 'customer-crowds':'/qos/shopbank/crowd_operate',
 'content-overview':'/xsite/contentanalysis/overview_new_v2','content-live-performance':'/xsite/contentanalysis/lives/performance',
 'service-core':'/qos/service/core_monitor/new','service-realtime':'/qos/service/frame/realtime_report',
 'service-shop-performance':'/qos/service/frame/shop/performance/new','service-staff-performance':'/qos/service/frame/customer/performance/new',
 'service-custom-reports':'/qos/service/self_made_report','service-after-sale':'/qos/service/after_sale/activist',
 'service-experience':'/qos/frame/cds/experience','service-logistics':'/qos/frame/cds/logistics/qn',
}.items()})
PAGES.update({
 "market-ranking": "https://sycm.taobao.com/mc/free/market_rank",
 "market-14382": "https://sycm.taobao.com/mc/free/d11_market_rank",
 "market-14050": "https://sycm.taobao.com/mc/free/market_insight",
 "market-14051": "https://sycm.taobao.com/mc/free/hot_detail",
 "market-14052": "https://sycm.taobao.com/mc/free/style_detail",
 "market-14053": "https://sycm.taobao.com/mc/free/factor_detail",
 "market-13860": "https://sycm.taobao.com/mc/free/search_rank",
 "market-13884": "https://sycm.taobao.com/mc/free/search_analysis",
 "market-14126": "https://sycm.taobao.com/mc/free/channel_goods",
 "market-13861": "https://sycm.taobao.com/mc/free/class_dig",
 "market-13862": "https://sycm.taobao.com/mc/free/class_analysis",
 "market-13863": "https://sycm.taobao.com/mc/free/ci_monitor",
 "market-14083": "https://sycm.taobao.com/mc/free/ci_shop_loss",
 "market-14084": "https://sycm.taobao.com/mc/free/ci_item_loss",
 "market-13865": "https://sycm.taobao.com/mc/free/ci_shop",
 "market-13866": "https://sycm.taobao.com/mc/free/ci_item",
 "zone-information-flow": "https://sycm.taobao.com/xsite/shoutao/information-flow.htm",
 "zone-14349": "https://sycm.taobao.com/xsite/frame/flash",
 "zone-14249": "https://sycm.taobao.com/xsite/frame/bybt",
 "zone-14158": "https://sycm.taobao.com/datawar/bybt",
 "zone-14269": "https://sycm.taobao.com/xsite/frame/jhs",
 "zone-14226": "https://sycm.taobao.com/xsite/frame/taojinbi",
 "zone-12405": "https://sycm.taobao.com/xsite/frame/shunshoumaiyijian_report",
 "zone-12113": "https://sycm.taobao.com/xsite/frame/pay_later_report",
 "zone-14394": "https://sycm.taobao.com/xsite/frame/item/subao",
 "zone-10409": "https://sycm.taobao.com/xsite/frame/yingxiaozuanqu.htm",
 "zone-12090": "https://sycm.taobao.com/xsite/frame/shopsmallroutine",
 "zone-12030": "https://sycm.taobao.com/xsite/frame/stmoversea",
 "zone-14380": "https://sycm.taobao.com/xsite/frame/fushi/queshou",
 "zone-10265": "https://sycm.taobao.com/xsite/group-chat/index.htm",
 "zone-14398": "https://sycm.taobao.com/xsite/frame/content/grass",
 "zone-10271": "https://sycm.taobao.com/xsite/frame/tvtaobao",
 "zone-14401": "https://sycm.taobao.com/xsite/frame/recommend_grass",
 "zone-12112": "https://sycm.taobao.com/xsite/frame/interest_free_report",
 "zone-12114": "https://sycm.taobao.com/xsite/frame/brand_member_report",
 "zone-14322": "https://sycm.taobao.com/xsite/frame/pc/purchasing",
 "zone-12752": "https://sycm.taobao.com/xsite/frame/student_sale",
 "zone-12894": "https://sycm.taobao.com/xsite/frame/after_purchase_video",
 "zone-13508": "https://sycm.taobao.com/xsite/frame/baiyibutie",
 "zone-14403": "https://sycm.taobao.com/xsite/frame/maomao_new",
 "zone-14044": "https://sycm.taobao.com/xsite/frame/baiyibutie/yibenzhang",
 "zone-13532": "https://sycm.taobao.com/xsite/frame/collocation_analyse",
 "zone-13534": "https://sycm.taobao.com/xsite/contentanalysis/nice_good",
 "zone-13536": "https://sycm.taobao.com/xsite/contentanalysis/duanshipin/shop_analysis",
 "zone-13542": "https://sycm.taobao.com/xsite/contentanalysis/subscribe/analysis",
 "zone-14236": "https://sycm.taobao.com/xsite/frame/tmall/youxian",
 "zone-13756": "https://sycm.taobao.com/xsite/frame/tianmao_business",
 "zone-13758": "https://sycm.taobao.com/xsite/frame/ticket_effect",
 "zone-13759": "https://sycm.taobao.com/xsite/frame/order_flow",
 "zone-14128": "https://sycm.taobao.com/xsite/frame/tmall/app/member",
 "zone-14321": "https://sycm.taobao.com/xsite/frame/special/price",
 "zone-14070": "https://sycm.taobao.com/xsite/frame/flash/sell"
})
WRITE=re.compile(r'(^|[/.])(add|create|update|delete|remove|save|submit|cancel|set|edit|upload|apply|bind|unbind)([/.]|$)',re.I)

def validate_asset(url):
 u=urlsplit(url)
 path_allowed=re.fullmatch(r'/dt/(?:sycm-[A-Za-z0-9_-]+|ops-flow|op-fa|op-live|op-sales|op-cc|op-service|op-cp|op-market|oneness-page)/[A-Za-z0-9_./-]+\.js',u.path) or re.fullmatch(r'/dt/ops-bda/1\.0\.15/js/trade/(?:overview|constitute)/app\.js',u.path)
 path_allowed=path_allowed or re.fullmatch(r'/aligenius/customer-service-performance/[0-9.]+/[A-Za-z0-9_./-]+\.js',u.path)
 path_allowed=path_allowed or re.fullmatch(r'/qbi/qbi/[0-9.]+/[A-Za-z0-9_./~-]+\.js',u.path)
 path_allowed=path_allowed or u.path=='/dt/ops-base/1.0.11/js/ops-base.js'
 if u.scheme!='https' or u.netloc!='g.alicdn.com' or u.query or u.fragment or '%' in u.path or '..' in u.path or not path_allowed:raise ValueError('Only observed public SYCM JavaScript assets without credentials/query are supported')
 return url

def validate_page(name):
 if name not in PAGES:raise ValueError('Only registered official SYCM pages are supported')
 return PAGES[name]

def parse_source(text,url):
 class Parser(HTMLParser):
  def __init__(self):super().__init__();self.scripts=[];self.runtime_metadata={}
  def handle_starttag(self,tag,attrs):
   if tag=='meta':
    content=dict(attrs).get('content','')
    for key,value in re.findall(r'([A-Za-z][A-Za-z0-9_]*)=([^;\s]+)',content):
     if re.fullmatch(r'ctxCSP|ctx[A-Za-z0-9_]*Version|[A-Za-z_]*(?:PageCode|pageCode|ProjectName|projectName)',key) and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',value):self.runtime_metadata[key]=value
   if tag=='script':
    src=dict(attrs).get('src')
    if src:
     u=urlsplit(urljoin(url,src))
     if u.scheme=='https' and not u.username and not u.password:self.scripts.append(u._replace(query='',fragment='').geturl())
 p=Parser()
 if not urlsplit(url).path.endswith('.js'):p.feed(text)
 paths=sorted({x for x in re.findall(r'[\"\x27`]((?:/flow/|/portal/|/cc/|/ipoll/|/fa/|/bda/|/xsite/|/s_content/|/csp/)[A-Za-z0-9_./-]+\.json)[\"\x27`]',text) if not WRITE.search(x)})
 # Official market trend statistics have no .json suffix; keep the exact
 # observed read routes rather than widening discovery to all suffixless URLs.
 paths=sorted(set(paths)|set(re.findall(r'[\"\x27`](/s_portal/fashion/trend/(?:categories|filters|rankings|seller-items))[\"\x27`]',text)))
 static_refs=sorted(set(re.findall(r'(?:https:)?//g\.alicdn\.com/[A-Za-z0-9_./~-]+(?:\.js|\.html|\.json)',text)))
 bootstrap_paths=sorted(set(re.findall(r'[\"\x27`](/[A-Za-z0-9_./-]+\.json)[\"\x27`]',text)))
 bootstrap_static=sorted(set(re.findall(r'(?:https:)?//g\.alicdn\.com/[A-Za-z0-9_./-]+',text)))
 inline_keys=sorted(set(re.findall(r'(?:window\.)?([A-Za-z_$][\w$.]{1,80})\s*=',text))) if not url.endswith('.js') else []
 versions=re.findall(r'ctxSFlowVersion\s*=\s*[\"\x27]?([0-9]+(?:\.[0-9]+)+)',text)
 versions+=re.findall(r'name=[\"\x27]ctxSFlowVersion[\"\x27][^>]*content=[\"\x27]([0-9.]+)[\"\x27]',text)
 derived=[f'https://g.alicdn.com/dt/ops-flow/{v}/{name}.js' for v in sorted(set(versions)) for name in ('app','vendors')]
 project_versions={}
 for key,project in [('ctxFaVersion','op-fa'),('ctxLiveVersion','op-live'),('ctxSalesVersion','op-sales'),('ctxCcVersion','op-cc'),('ctxServiceVersion','op-service'),('ctxCpVersion','op-cp'),('ctxMarketVersion','op-market'),('ctxOnenessPageVersion','oneness-page')]:
  found=re.findall(r'name=[\"\x27]'+key+r'[\"\x27][^>]*content=[\"\x27]([0-9.]+)[\"\x27]',text)
  found+=re.findall(key+r'\s*=\s*[\"\x27]?([0-9]+(?:\.[0-9]+)+)',text)
  found+=re.findall(key+r'[\"\x27]?\s*:\s*[\"\x27]([0-9.]+)[\"\x27]',text)
  if found:project_versions[project]=found[0]
 derived_projects=[f'https://g.alicdn.com/dt/{project}/{version}/{name}.js' for project,version in project_versions.items() for name in ('app','vendors')]
 chunks=[];base=re.search(r'\w+\.p=[\"\x27](//g\.alicdn\.com/dt/(?:ops-flow|op-fa|op-live|op-sales|op-cc|op-service|op-cp|op-market|oneness-page)/[0-9.]+/)[\"\x27]',text)
 names=re.search(r'\w+\.src=function\(e\).*?\(\{(.*?)\}\[e\]\|\|e\)\+[\"\x27]\.js',text)
 if base and names:
  mapping=dict(re.findall(r'(\d+):[\"\x27]([A-Za-z0-9_-]+)[\"\x27]',names.group(1)))
  chunks=['https:'+base.group(1)+mapping.get(i,i)+'.js' for i in sorted(set(mapping)|set(re.findall(r'\b\w+\.e\((\d+)\)',text)),key=int)]
 if '/qbi/qbi/' in url:
  loader=re.search(r'\w+\.src=function\(\w+\)\{(.+?)\}\(\w+\)',text)
  if loader and '.chunk.js' in loader.group(1):
   pairs=re.findall(r'(\d+):[\"\x27]([a-f0-9]{4,})[\"\x27]',loader.group(1))
   chunks.extend(url.rsplit('/',1)[0]+'/'+i+'.'+digest+'.chunk.js' for i,digest in pairs)
 return {'source_url':url,'sha256':hashlib.sha256(text.encode()).hexdigest(),'characters':len(text),'scripts':list(dict.fromkeys(p.scripts)),'runtime_metadata':p.runtime_metadata,'candidate_paths':paths,'static_references':static_refs,'bootstrap_static_urls':bootstrap_static,'flow_versions':versions,'derived_flow_assets':derived,'project_versions':project_versions,'derived_project_assets':derived_projects,'chunk_asset_references':chunks,'derivation':'Official micro-v2 resource template and page version metadata; never executed','bootstrap_paths':bootstrap_paths,'status':'candidates_not_verified'}

def collect(args):
 from .cli import load_taobao_cookies
 from ...core import transport
 from ...core.errors import TbError
 url=validate_page(args.page);cookies=load_taobao_cookies();client=cookies.client
 if not getattr(client,'_bridge_server',None):raise TbError('Discovery requires the extension-backed MCP transport')
 try:
  if args.asset_url:
   asset=validate_asset(args.asset_url)
   byte_range=None
   if getattr(args,'byte_range',None):
    if not re.fullmatch(r'\d+:\d+',args.byte_range):raise ValueError('Use --byte-range START:END')
    byte_range=list(map(int,args.byte_range.split(':')))
    if byte_range[1]<byte_range[0] or byte_range[1]-byte_range[0]+1>1048576:raise ValueError('Public source range must be at most one MiB')
   if not args.evidence:raise ValueError('--asset-url requires --evidence from previous discovery')
   evidence=json.loads(Path(args.evidence).read_text(encoding='utf8'))
   if asset not in evidence.get('scripts',[])+evidence.get('asset_references',[])+evidence.get('derived_flow_assets',[])+evidence.get('derived_project_assets',[])+evidence.get('chunk_asset_references',[])+(evidence.get('page_source') or {}).get('scripts_without_queries',[]):raise ValueError('Asset was not observed in source evidence')
   from ...core.bridge import version_tuple
   minimum='0.9.55' if '/qbi/qbi/' in asset else '0.9.53' if any('/dt/'+x+'/' in asset for x in ('op-market','oneness-page')) else '0.9.52' if '/dt/op-cp/' in asset else '0.9.51' if '/dt/ops-base/' in asset else '0.9.49' if '/aligenius/customer-service-performance/' in asset else '0.9.48' if '/dt/op-service/' in asset else '0.9.47' if '/dt/ops-bda/' in asset else '0.9.45' if '/dt/op-' in asset else '0.9.43'
   if byte_range and version_tuple(minimum)<version_tuple('0.9.50'):minimum='0.9.50'
   if version_tuple(client._bridge_server.extension_version)<version_tuple(minimum):raise TbError('Public asset discovery needs bridge '+minimum+'; refresh shopdate-cli extension once')
   result=client._bridge_server.submit({'url':asset,'public_asset':True,**({'byte_range':byte_range} if byte_range else {})},60)
   if result.get('error'):raise TbError(str(result['error']))
   from types import SimpleNamespace
   response=SimpleNamespace(status_code=result.get('status'),text=result.get('text',''),url=asset);url=asset
  else:
   client._guard();response=client.session.get(url,timeout=60)
  if response.status_code not in ((206,) if args.asset_url and getattr(args,'byte_range',None) else (200,)):raise TbError('Official page returned HTTP '+str(response.status_code))
  text=response.text
  # Public JS can contain verification UI strings as ordinary code. Only a
  # challenge document (or an authenticated page) is verification evidence.
  if (not args.asset_url or text.lstrip().lower().startswith(('<!doctype','<html'))) and any(s in text for s in ['请完成安全验证','验证码','滑块验证']):raise TbError('Security verification required; stop and ask user to complete it')
  if 'login' in (response.url or '').lower():raise TbError('Login expired; stop')
  if len(text)>5000000:raise TbError('Source exceeds bounded discovery limit')
  content_range=result.get('content_range') if args.asset_url else None
  result=parse_source(text,url);result['transport']='shopdate_symc_MCP_extension';result['observed_at']=time.strftime('%Y-%m-%dT%H:%M:%S%z')
  if args.asset_url and getattr(args,'byte_range',None):result.update(partial_source=True,content_range=content_range,byte_range=byte_range)
  refs=[]
  for link in re.findall(r'(?:https:)?//g\.alicdn\.com/[A-Za-z0-9_./~-]+\.js',text):
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
 from . import business_queries
 business_queries.register(sp)
 from . import module_queries
 module_queries.register(sp)
 from . import protocol_queries
 protocol_queries.register(sp)
 from . import market_queries
 market_queries.register(sp)
 p=sp.add_parser('interface-discover',help='通过MCP只读数据桥发现官方流量、营销、交易、商品、客户、内容和服务页面引用，不执行页面脚本')
 p.add_argument('--page',choices=tuple(PAGES),required=True);p.add_argument('--asset-url');p.add_argument('--byte-range');p.add_argument('--evidence');p.add_argument('--out');p.set_defaults(func=collect)
