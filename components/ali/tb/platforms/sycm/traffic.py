"""Historical full-shop traffic reads, discovered in official ops-flow 2.0.185.

Online access is exclusively through the existing shopdate_symc MCP bridge.
Source visitors and attributed sales overlap; never aggregate tree rows.
"""
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

BOARD = 'https://sycm.taobao.com/flow/monitor/overview'
SOURCE = 'https://sycm.taobao.com/flow/monitor/shopsource/construction'
COMMANDS = {
    'traffic-overview': ('/flow/new/guide/trend/overview.json', '流量看板历史概览'),
    'traffic-trend': ('/flow/new/guide/trend.json', '流量看板历史趋势'),
    'shop-source-overview': ('/flow/shop/source/overview/v4.json', '店铺来源历史总览'),
    'shop-source-tree': ('/flow/v5/shop/source/tree/v4.json', '全店来源渠道树（访客与归因成交存在重叠）'),
}
METRICS = ('uv', 'pv', 'payByrCnt', 'payAmt', 'payRate', 'payPct', 'payItmCnt', 'cartByrCnt', 'cltItmCnt')


def build_request(command, start, end=None, *, today=None, page_type='all'):
    first, last = date.fromisoformat(start), date.fromisoformat(end or start)
    today = today or datetime.now(timezone(timedelta(hours=8))).date()
    days = (last - first).days + 1
    if last >= today or days not in (1, 7):
        raise ValueError('Only complete historical days or native seven-day periods are supported')
    path = COMMANDS[command][0]
    params = {'dateType': 'day' if days == 1 else 'recent7', 'dateRange': f'{first}|{last}'}
    if command.startswith('traffic-'):
        params.update(device='0', indexCode='uv,itmUv,payByrCnt', dtMaxAge=15000)
        if command == 'traffic-trend':
            params['type'] = '1'  # Official overviewBoardV2 scopePageState.trendType.
        return path, params, BOARD
    params.update(needCate='true', dtMaxAge=7200000)
    if command == 'shop-source-tree':
        if page_type not in ('all', 'item', 'shop', 'live', 'content'):
            raise ValueError('Unsupported official pageType')
        params.update(flowBizType='all', pageType=page_type, belong='all', crowdType='all',
                      indexCode=','.join(METRICS), orderBy='uv', order='desc')
        # Official AllFlowTableLazy hasPage:false. Preserve the returned tree;
        # do not invent page sizes or claim completion of lazy detail channels.
    return path, params, SOURCE


def value(row, key):
    field = row.get(key)
    return field.get('value') if isinstance(field, dict) else field


def flatten_tree(rows):
    result = []
    for row in rows:
        result.append({key: value(row, key) for key in
                       ('pageId', 'pPageId', 'pageName', 'pageLevel', 'showDetailChannel') + METRICS})
        result.extend(flatten_tree(row.get('children') or []))
    return result


def summarize(command, response):
    data = response.get('data')
    if command == 'traffic-trend':
        return {'data': data, 'coverage': 'server_trend_window',
                'returned_axis': (data or {}).get('my', {}).get('statDate', []),
                'request_window_guaranteed': False,
                'notes': ['Official type=1 returns a server-selected trailing trend window, observed as 30 days.',
                          'Use returned my.statDate; do not label all points as the requested dateRange.',
                          'The MM-DD axis does not include a year; preserve the request end date as context.']}
    if command == 'shop-source-tree':
        rows = flatten_tree(data) if isinstance(data, list) else []
        return {'rows': rows, 'row_count': len(rows), 'additive': False,
                'coverage': 'returned_tree_only',
                'notes': ['UV and attributed payments overlap across channels and levels.',
                          'Returned nested levels only; lazy detail-channel expansion is not claimed complete.',
                          'SYCM attributed payments are not Alimama ad-attributed sales or ROI.']}
    return {'data': data, 'coverage': 'official_response',
            'notes': ['Source overview and traffic board may use different coverage; retain both totals.',
                      'Native seven-day visitors are period-deduplicated; do not sum daily UV.']}


def collect(args):
    from .cli import load_taobao_cookies, _api_get
    from ...core import transport
    from ...core.errors import TbError
    path, params, referer = build_request(args.command, args.date, args.end_date,
                                          page_type=getattr(args, 'page_type', 'all'))
    cookies = load_taobao_cookies()
    client = cookies.client
    try:
        if not getattr(client, '_bridge_server', None):
            raise TbError('Traffic commands require the extension-backed MCP transport')
        response = _api_get(path, {**params, '_': str(int(time.time() * 1000)),
                                   'token': cookies.get('_tb_token_', '')}, cookies, referer=referer)
        if response.get('code') not in (0, '0') or response.get('data') is None:
            raise TbError('Official traffic response is unsuccessful or has no data; not treated as zero')
        result = {'source': 'shopdate_symc_MCP_extension', 'command': args.command,
                  'observed_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
                  'request': {'path': path, 'params': params, 'referer': referer},
                  'status': 'empty' if response['data'] in ([], {}) else 'ok',
                  'summary': summarize(args.command, response), 'response': response}
        if args.out:
            target = Path(args.out)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
            print(json.dumps({'status': result['status'], 'out': str(target),
                              'command': args.command, 'dateRange': params['dateRange'],
                              'coverage': result['summary']['coverage'],
                              'row_count': result['summary'].get('row_count')}, ensure_ascii=False))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        transport.release(client)


def register(sp):
    for name, (_, description) in COMMANDS.items():
        p = sp.add_parser(name, help=description)
        p.add_argument('--date', required=True, help='完整历史日，或七日期间的开始日 YYYY-MM-DD')
        p.add_argument('--end-date', help='七日期间的结束日；不填则取单日')
        p.add_argument('--out', help='保存完整原始返回与口径说明，避免明细截断')
        if name == 'shop-source-tree':
            p.add_argument('--page-type', choices=('all', 'item', 'shop', 'live', 'content'), default='all')
        p.set_defaults(func=collect, command=name)
