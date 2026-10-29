"""Isolated source worker: import exactly one platform's tb package per process."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from .evidence import write_evidence
from .metrics import window

ROOT=Path(__file__).resolve().parents[1]


def verify_symc_identity(current,store):
    if not current.get('loggedIn') or 'sycm:account:'+str(current.get('uid',''))!=store:
        raise ValueError('当前天猫账号身份与指定store_key不符，停止取数。')


def symc_rows(table,store):
    return [{'platform':'symc','store_key':store,'date':day,
             'values':{field:obj.get('value') if isinstance(obj,dict) else obj
                       for field,obj in values.items()}}
            for day,values in sorted(table.items())]


def current_symc(server=None):
    from tb.core import accounts
    owned=server is None
    server=server or accounts._connect()
    try:
        current=accounts._ask(server,'list')['current'].get('taobao',{})
        # Only non-sensitive account identity is retained; no snapshots/cookies.
        return {key:current.get(key) for key in ('uid','nick','loggedIn')}
    finally:
        if owned:server.stop()


def collect(platform,store,dates,checkpoint,seed=None,refresh=False):
    from .reuse import prepare_reuse
    reuse=prepare_reuse(seed,platform,store,dates,refresh) if seed is not None else {
        'rows':[],'sources':[],'reused_dates':[],'pending_dates':list(dates)}
    started=time.perf_counter()
    payload={'platform':platform,'store_key':store,'rows':reuse['rows'],'sources':reuse['sources'],
        'identity_verified':False,'verified_dates':reuse['reused_dates'][:],
        'reused_dates':reuse['reused_dates'],'fresh_dates':[],
        'acquired_at':datetime.now(timezone.utc).isoformat(),
        'cached_source_acquired_at':seed.get('acquired_at') if seed else None}
    def checkpoint_save():
        payload['rows'].sort(key=lambda row:row['date'])
        payload['sources'].sort(key=lambda row:row['date'])
        payload['verified_dates']=sorted(set(payload['verified_dates']))
        write_evidence(checkpoint,payload)
    if not reuse['pending_dates']:
        payload.update(identity_verified=True,acquired_at=seed.get('acquired_at'),
                       overview_request_count=0,collection_ms=0)
        if seed.get('grow_factor',{}).get('date')==dates[-1]:payload['grow_factor']=seed['grow_factor']
        checkpoint_save();return payload
    root=ROOT if platform=='jd' else (ROOT.parent/'ali').resolve()
    loaded=sys.modules.get('tb')
    if loaded is not None and Path(loaded.__file__).resolve().parent.parent!=root.resolve():
        raise ValueError('同名tb包已载入另一平台；请通过独立CLI/MCP命令运行。')
    sys.path.insert(0,str(root));os.environ['PYTHONPATH']=str(root)
    os.chdir(root)
    if platform=='jd':
        from tb.platforms.jd.api_client import APIClient,capture_api
        from tb.platforms.jd import overview,reports
        template=reports.contracts()['overview']['template']
        with APIClient({'platform':'jd','store_key':store}) as client:
            for day in reuse['pending_dates']:
                result=capture_api('overview',day,store,client=client)
                report=overview.summarize(json.loads(result['text']),overview.make_request(template,day))
                if result['identity'].get('store_key')!=store:
                    raise ValueError('京东响应店铺不符。')
                payload['rows'].append({'platform':'jd','store_key':store,'date':day,
                    'compare_date':report['compare_date'],
                    'comparisons':{m['field']:m['previous'] for m in report['metrics']},
                    'values':{m['field']:m['value'] for m in report['metrics']}})
                payload['sources'].append({'date':day,'command':'shop-overview',
                    'raw':json.loads(result['text']),'identity':result['identity'],
                    'request_timestamp':result['request_timestamp']})
                payload['verified_dates'].append(day);payload['fresh_dates'].append(day)
                checkpoint_save()
        payload['identity_verified']=True
    else:
        from tb.platforms.sycm import cli
        from tb.core import transport
        before=current_symc();verify_symc_identity(before,store)
        payload['identity_before']=before
        try:
            # Reuse one existing SYCM client; serial daily requests, no concurrent bridge.
            cookies=cli.load_taobao_cookies()
            for day in reuse['pending_dates']:
                table=cli.fetch_home_table(day,day,cookies=cookies)
                # Same bridge: no second listener or competing account connection.
                identity=current_symc(getattr(cookies.client,'_bridge_server',None))
                verify_symc_identity(identity,store)
                payload['rows'].extend(symc_rows(table,store))
                payload['sources'].append({'date':day,'command':'home-table','raw':table,
                    'request_timestamp':datetime.now(timezone.utc).isoformat()})
                payload['verified_dates'].append(day);payload['fresh_dates'].append(day)
                checkpoint_save()
            if len(dates)==7:
                try:
                    response=cli._fetch_order_portal('/portal/board/grow/factor/overview.json',
                        date_value=dates[-1],extra={'device':'2'},cookies=cookies)
                    payload['grow_factor']={'status':'ok','date':dates[-1],
                        'self':cli._content_data_or_error(response).get('self'),
                        'note':'组件不能相加当作GMV；不输出竞品数据'}
                except Exception as error:
                    # Do not retry or continue after authentication/security failures.
                    text=str(error)
                    if any(word in text.lower() for word in ('605','验证码','滑块','登录','login','captcha')):
                        raise
                    payload['grow_factor']={'status':'unavailable','error_type':type(error).__name__}
        finally:
            if cli._CLIENT is not None:
                transport.release(cli._CLIENT);cli._CLIENT=None
        after=current_symc();verify_symc_identity(after,store)
        payload['identity_after']=after;payload['identity_verified']=True
    payload['collection_ms']=round((time.perf_counter()-started)*1000)
    payload['overview_request_count']=len(reuse['pending_dates'])
    checkpoint_save()
    return payload


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--platform',choices=['jd','symc'],required=True)
    parser.add_argument('--store',required=True)
    parser.add_argument('--date',required=True)
    parser.add_argument('--task',choices=['daily','weekly'],required=True)
    parser.add_argument('--checkpoint',required=True)
    args=parser.parse_args()
    try:
        dates=window(args.platform,args.store,args.date,args.task)
        collect(args.platform,args.store,dates,Path(args.checkpoint).resolve())
        print(json.dumps({'evidence_path':args.checkpoint}))
        return 0
    except Exception as error:
        # Keep platform diagnostics on stderr; never return raw authenticated payloads.
        print('取数未完成：'+type(error).__name__+'；'+str(error),file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
