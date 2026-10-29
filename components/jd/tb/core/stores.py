"""Read-only browser identity discovery; no cookie snapshots or login switching."""
import argparse
import json
import re
import time
from pathlib import Path
from .platform import Platform
from .bridge import BridgeServer


class StoreRows(list):
    """List-compatible identities with non-sensitive handoff timing evidence."""
    def __init__(self,rows,bridge_timings=None,discovery=None):
        super().__init__(rows)
        self.bridge_timings=bridge_timings
        self.discovery=discovery


def choose_store(rows, platform, store):
    if platform not in ('jd','sycm'):
        raise ValueError('必须指定 platform=jd 或 sycm，不能仅凭同名店铺选择。')
    candidates=[r for r in rows if r.get('platform')==platform and (not store or store in (r.get('store_key'),r.get('name')))]
    if not candidates and not any(r.get('platform')==platform for r in rows):
        raise ValueError('当前未能确认店铺身份；不等于登录失效。页面可能尚未响应，请重新检查 stores。')
    if len(candidates)!=1:
        raise ValueError('店铺不存在或不唯一，请先列出 stores，再使用平台及完整 store_key。')
    return candidates[0]


def verify_identity(expected, actual):
    if not actual or any(expected.get(k)!=actual.get(k) for k in ('platform','store_key')) or not actual.get('store_key'):
        raise ValueError('当前浏览器身份与指定店铺不符，停止，未将其他店铺数据作为结果。')


def discover(platform=''):
    if platform not in ('','jd','sycm'):raise ValueError('不支持的平台。')
    # This derivative's default is JD only. Its identity queue must not attach
    # to a permanently running SYCM service or wait behind JD data collection.
    platform=platform or 'jd'
    isolated=platform=='jd';page='https://jdsz.jd.com/szweb/view/index/home.html'
    bridge=BridgeServer(Platform(name='jd-stores' if isolated else 'stores',display='店铺身份识别',hosts={},login_page='',launch_url=page if isolated else '',
       login_cookies=(),cookie_domains=(),referer='',expired_hints=(),write_re=re.compile('.*'),env_prefix='JD_STORES' if isolated else 'TB_STORES',min_extension='0.9.9' if isolated else None))
    started=False
    tick=time.monotonic()
    try:
        bridge.start(lock_wait=2)
        started=True
        # Identity checks must not inherit the 15-minute report lock queue.
        # Include lock acquisition in the 20-second discovery budget.
        attempts=[]
        for attempt in range(2 if platform=='jd' else 1):
            remaining=20-(time.monotonic()-tick)
            if remaining<=0:raise TimeoutError('店铺身份诊断超时；不据此判定登录失效。')
            job={'store_request':{'platform':platform},'url':page if isolated else 'https://sycm.taobao.com/robots.txt'}
            if isolated:job['transport']='jd-identity'
            result=bridge.submit(job,timeout=remaining)
            if result.get('error'):raise ValueError(result['error'])
            rows=result.get('stores')
            if not isinstance(rows,list):raise ValueError('扩展没有返回店铺列表；请更新统一数据桥。')
            attempts.append({'store_count':len(rows),'bridge_timings':result.get('bridge_timings')})
            # A completed empty DOM read can race a waking page. Re-read once,
            # never retry an error/other store, never renew the total budget.
            if platform=='jd' and not rows and attempt==0:continue
            diagnostic={'state':'confirmed' if rows else 'unknown','recovered':len(attempts)>1 and bool(rows),
              'attempts':attempts,'elapsed_ms':round((time.monotonic()-tick)*1000)}
            return StoreRows(rows,result.get('bridge_timings'),diagnostic)
    finally:
        if started:bridge.stop()
        else:bridge.server_close()


def main(argv):
    ap=argparse.ArgumentParser(description='列出当前浏览器可识别的平台身份，不切换登录。')
    ap.add_argument('action',choices=['list'])
    ap.add_argument('--platform',choices=['jd','sycm'],default='')
    args=ap.parse_args(argv)
    rows=discover(args.platform)
    print(json.dumps({'stores':rows,'bridge_timings':getattr(rows,'bridge_timings',None),'discovery':getattr(rows,'discovery',None)},ensure_ascii=False,indent=2))
    return 0
