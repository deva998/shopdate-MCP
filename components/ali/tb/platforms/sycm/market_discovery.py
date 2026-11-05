"""MCP-only passive market sampling and fixed official recruitment source reads."""
import json,re
from dataclasses import replace
from datetime import datetime,timezone,timedelta
from pathlib import Path
from .platform import SYCM
from .market_queries import PAGES
from ...core import transport

RECRUIT_PAGES={
 'seller':'https://qn.taobao.com/microapp/qn-tmc-bidding/bidding/seller/bybt_race_price_site.htm?isInIframe=true&source=127&biddingSource=sycmsy',
 'seckill':'https://qn.taobao.com/microapp/ltao-home/coreActivity?gpReqChannelParam=180008',
 'sale':'https://qn.taobao.com/microapp/starb/bidding/sale/race/square?channel=sycm',
 'quick-sale':'https://qn.taobao.com/microapp/ltao-home/quickSale?tab=item&type=potential&onlyShowCard=ab&channelId=sycmbd',
 'trend':'https://qn.taobao.com/microapp/trend-product-operation/opportunityTab?code=trend&from=sycm',
 'season':'https://qn.taobao.com/microapp/trend-product-operation/opportunityTab?code=season&from=sycm',
}
def recruit_url(name):
 if name not in RECRUIT_PAGES:raise ValueError('Only source-declared fixed recruitment pages are allowed')
 return RECRUIT_PAGES[name]

def source_summary(text,url):
 from .interface_discovery import parse_source
 if any(x in text for x in ('_____tmd_____','x5secdata','FAIL_SYS_USER_VALIDATE','RGV587_ERROR')):return {'status':'security_verification','business_statistics_verified':False}
 if re.search(r'type=["\x27]password',text,re.I):return {'status':'login_required','business_statistics_verified':False}
 r=parse_source(text,url);r['status']='definition_only' if r.get('scripts') else 'source_without_scripts';r['business_statistics_verified']=False;r['raw_HTML_saved']=False
 r['mtop_method_literals']=sorted(set(re.findall(r'["\x27](mtop\.[A-Za-z0-9_.]+)["\x27]',text)))
 return r

def emit(args,out):
 out.update(source='shopdate_symc_MCP_extension',observed_at=datetime.now(timezone(timedelta(hours=8))).isoformat())
 if args.out:
  p=Path(args.out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(out,ensure_ascii=False,indent=2))

def observe(args):
 client=transport.make_client(replace(SYCM,min_extension='0.9.62',extension_only=True))
 try:
  client._guard();raw=client._bridge_server.submit({'url':'https://sycm.taobao.com/mc/free/'+PAGES[args.page],'sycm_market_observe':args.action},45)
  response=client.session._reply(raw);emit(args,json.loads(response.text))
 finally:transport.release(client)

def recruit_source(args):
 target=recruit_url(args.entry)
 plat=replace(SYCM,hosts={**SYCM.hosts,'view':'https://qn.taobao.com'},launch_url='https://qn.taobao.com/robots.txt',readable_cookies=(),extension_only=True,min_extension='0.9.62')
 client=transport.make_client(plat);out={'entry':args.entry,'business_statistics_verified':False,'status':'error'}
 try:
  client._guard();response=client.session.get(target,timeout=60)
  if response.status_code!=200:raise ValueError('Official page HTTP '+str(response.status_code))
  if len(response.text)>5000000:raise ValueError('Official page exceeds bounded source limit')
  out.update(source_summary(response.text,target))
 except Exception as error:out.update(error_type=type(error).__name__,error=re.sub(r'https?://\S+','[URL omitted]',str(error)))
 finally:transport.release(client);emit(args,out)

def register(sp):
 p=sp.add_parser('market-observe',help='只读被动记录市场当前页本轮新增请求地址/脱敏筛选；两分钟上限，不操作页面、不修改请求')
 p.add_argument('--page',choices=tuple(PAGES),required=True);p.add_argument('--action',choices=('start','read','stop'),required=True);p.add_argument('--out');p.set_defaults(func=observe)
 p=sp.add_parser('market-recruit-source',help='MCP只读官方源码已声明的6个平台热招千牛入口；仅核对HTML结构，不算业务统计')
 p.add_argument('--entry',choices=tuple(RECRUIT_PAGES),required=True);p.add_argument('--out');p.set_defaults(func=recruit_source)
