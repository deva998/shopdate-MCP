"""Registered industry reads; official intervals stay raw and are never decoded."""
import argparse
from datetime import date,datetime,timedelta,timezone
import json
from pathlib import Path
import re
import sys
from uuid import uuid4

PAGE='https://jdsz.jd.com/szweb/view/industry/industrySummary.html'
RANK_PAGE='https://jdsz.jd.com/szweb/view/industry/industry-top.html'
HOST='https://szgateway.jd.com'
ROUTES={
    'industry-options':('GET',HOST+'/api/common/getDims.ajax?menuCode=industrySummary',PAGE),
    'industry-overview':('POST',HOST+'/api/lowcode/industrySummary/core/summaryv2.ajax',PAGE),
    'industry-products':('POST',HOST+'/api/lowcode/industryTop/indProductRank/productRank.ajax',RANK_PAGE),
    'industry-shops':('POST',HOST+'/api/lowcode/industryTop/indShopRank/shopRankList.ajax',RANK_PAGE)}
FIELDS={'channel','popBusiness','dateType','startDate','endDate','compareType','compareStartDate',
    'compareEndDate','realtime','interval','indicators','rankTab','sortField','sortOrder','skuSpuType',
    'saleOrdCate2','saleOrdCate3','bsIndCate2','bsIndCate3','onlySelf','onlyMonitor'}
METRICS=[
    'jdr_sch_trade_deal_ord_ord_amt_sz_trade_deal_snapshot',
    'jdr_sch_trade_deal_ord_ord_qtty_sz_trade_deal_snapshot',
    'jdr_sch_trade_deal_ord_sku_qtty_sz_trade_deal_snapshot',
    'jdr_sch_traffic_brow_sku__page_cnt_traffic_plat_item_di_sz_bsg',
    'jdr_sch_traffic_brow_sku__page_qtty_traffic_plat_item_di_sz_bsg',
    'jdr_sch_search_click_page_qtty_search_standard_sz',
    'fo_jdr_sch_industry_deal_rate','fo_jdr_sch_trade_deal_ord_amt_user_sz_trade_deal_snapshot']


def build_request(options,kind,day,*,category,channel='all',business='pop',dimension='spu'):
    if kind not in ('overview','products','shops'):raise ValueError('未登记行业查询类型。')
    if options.get('header',{}).get('code')!=0:raise ValueError('官方筛选选项失败。')
    rows=options.get('body',{}).get('data')
    if not isinstance(rows,list):raise ValueError('缺少官方筛选结构。')
    dims={r['dimCode']:r for r in rows}
    def choose(code,query):
        hits=[r for r in dims.get(code,{}).get('dimVals',[]) if str(r.get('value'))==query or r.get('label')==query]
        if len(hits)!=1 or hits[0].get('disabled'):raise ValueError('官方筛选不存在、不唯一或不可选：'+str(query))
        return hits[0]['value']
    hits=[]
    def visit(nodes,path):
        for node in nodes:
            p=path+[node]
            if str(node.get('value'))==category or node.get('label')==category:hits.append(p)
            visit(node.get('children') or [],p)
    visit(dims.get('saleOrdCate',{}).get('dimVals',[]),[])
    if len(hits)!=1 or len(hits[0])>2 or any(r.get('disabled') for r in hits[0]):raise ValueError('官方类目不存在、不唯一或不可选；请用industry-options中的精确ID。')
    path=hits[0];prior=(date.fromisoformat(day)-timedelta(days=1)).isoformat()
    body={'startDate':day,'endDate':day,'compareStartDate':prior,'compareEndDate':prior,
        'compareType':'hb','dateType':'day','interval':'DAY','realtime':False,
        'saleOrdCate2':path[0]['value'],'popBusiness':choose('popBusiness',business),'channel':choose('channel',channel),
        'indicators':[x+y for x in METRICS for y in ('','##compare','##compareValue')] if kind=='overview' else list(METRICS)}
    if len(path)==2:body['saleOrdCate3']=path[1]['value']
    if kind!='overview':body.update(rankTab='hot',sortField=METRICS[0],sortOrder='desc')
    if kind=='products':
        if dimension not in ('spu','sku'):raise ValueError('维度必须为spu或sku。')
        body['skuSpuType']=dimension
    if kind=='shops':body.update(onlySelf='0',onlyMonitor='0')
    validate_request(body)
    return body,{'category_path':[r['label'] for r in path],'category_ids':[str(r['value']) for r in path],
        'channel':body['channel'],'business':body['popBusiness'],'ranking':'hot' if kind!='overview' else None,
        'dimension':dimension if kind=='products' else None,'date_scope':'single_complete_day'}


def validate_request(body,*,today=None):
    today=today or datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    if not isinstance(body,dict) or set(body)-FIELDS:raise ValueError('行业请求含未登记字段。')
    if any(isinstance(v,dict) or isinstance(v,list) and any(not isinstance(x,str) for x in v) for v in body.values()):
        raise ValueError('行业请求不接受嵌套对象或非字符串列表。')
    for name in ('startDate','endDate'):
        value=body.get(name)
        if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value) or date.fromisoformat(value).isoformat()!=value:
            raise ValueError('行业日期应为完整历史日。')
    if not body['startDate']<=body['endDate']<today:raise ValueError('行业查询仅允许完整历史区间。')
    for key in ('compareStartDate','compareEndDate'):
        if key in body:
            value=body[key]
            if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value) or date.fromisoformat(value).isoformat()!=value or value>=today:
                raise ValueError('行业比较日期无效。')
    if body.get('compareStartDate','')>body.get('compareEndDate','9999-12-31'):raise ValueError('行业比较区间顺序无效。')
    if body.get('realtime') is not False:raise ValueError('当前行业接口仅登记离线查询。')
    if not isinstance(body.get('indicators'),list) or not body['indicators'] or any(not isinstance(x,str) or not x for x in body['indicators']):
        raise ValueError('必须提供已核验的官方指标编码。')
    json.dumps(body,allow_nan=False)
    return body


def verify_proof(proof,command,day,store):
    from ...core.stores import verify_identity
    verify_identity({'platform':'jd','store_key':store},proof.get('identity'))
    if proof.get('case')!=command:raise ValueError('行业证据来源命令不符。')
    if command!='industry-options':
        request=validate_request(proof.get('request_body'))
        if request['startDate']!=day:raise ValueError('行业证据请求日期不符。')


def normalize(payload,kind,*,limit=100):
    if payload.get('header',{}).get('code')!=0 or payload.get('errors'):raise ValueError('行业接口业务失败。')
    body=payload.get('body')
    if not isinstance(body,dict):raise ValueError('缺少行业响应body。')
    if kind=='overview':
        if not isinstance(body.get('data'),list):raise ValueError('缺少官方行业概况列表。')
        return {'data':body,'coverage':{'scope':'official_industry_summary','precise_total_inferred':False}}
    if kind=='options':
        if not isinstance(body.get('data'),list):raise ValueError('缺少官方筛选列表。')
        return {'rows':body['data'],'coverage':{'scope':'authorized_official_filter_options','returned_rows':len(body['data'])}}
    if type(limit) is not int or not 1<=limit<=1000:raise ValueError('limit应为1至1000。')
    rows=body.get('data')
    if isinstance(rows,dict):rows=rows.get('list',rows.get('data'))
    if rows is None:rows=body.get('list')
    if not isinstance(rows,list) or any(not isinstance(x,dict) for x in rows):raise ValueError('缺少官方行业列表结构，不能当空表。')
    return {'rows':rows[:limit],'coverage':{'scope':'official_returned_ranking','returned_rows':len(rows),
        'output_rows':min(len(rows),limit),'output_truncated':len(rows)>limit,'all_market_products_complete':False,
        'note':'前端官方榜单不按pageSize翻页；保留返回榜单范围，不代表全行业全商品。'}}


def main(argv):
    from shopdate_workflows.evidence import read_evidence,write_evidence,save_json
    parser=argparse.ArgumentParser(description='京东行业只读查询。日期＋官方类目名称/ID查询大盘、热销商品榜和店铺榜；原始区间值不解码。')
    parser.add_argument('command',choices=list(ROUTES))
    parser.add_argument('--date',required=True,help='目标完整历史日；请求startDate必须一致')
    parser.add_argument('--store',required=True,help='精确jd:mall:...')
    parser.add_argument('--request-file',help='高级模式：纯官方查询JSON请求体，不含认证头/Cookie；不能与category混用')
    parser.add_argument('--category',help='官方类目精确名称或ID，重名必须使用ID')
    parser.add_argument('--channel',default='all',help='官方渠道值或名称，默认全部')
    parser.add_argument('--business',default='pop',help='官方经营模式值或名称，默认POP')
    parser.add_argument('--dimension',choices=['spu','sku'],default='spu')
    parser.add_argument('--evidence',help='本模块证据离线重放，不访问平台')
    parser.add_argument('--limit',type=int,default=100,help='仅截取已返回榜单，不是服务端分页')
    args=parser.parse_args(argv)
    try:
        if not 1<=args.limit<=1000:raise ValueError('limit应为1至1000。')
        if not re.fullmatch(r'jd:mall:\d+',args.store):raise ValueError('必须指定京东精确store_key。')
        day=date.fromisoformat(args.date)
        if day.isoformat()!=args.date or args.date>=datetime.now(timezone(timedelta(hours=8))).date().isoformat():raise ValueError('必须使用完整历史日。')
        if args.evidence and args.request_file:raise ValueError('离线重放不能混用新请求文件。')
        filter_flags={x.split('=',1)[0] for x in argv}&{'--category','--channel','--business','--dimension'}
        if (args.evidence or args.request_file) and filter_flags:
            raise ValueError('证据重放或请求文件不能同时指定category/channel/business/dimension；筛选范围只能有一个来源。')
        request_count=0;query_scope=None;options_proof=None;options=None
        if args.evidence:
            evidence=Path(args.evidence).resolve();payload=read_evidence(evidence,'jd',args.store)
            if payload.get('command')!=args.command or payload.get('date')!=args.date:raise ValueError('行业证据命令或日期不符。')
            raw=payload['response'];proof=payload['proof']
            query_scope=payload.get('query_scope')
        else:
            request=None
            if args.command!='industry-options':
                if not args.request_file and not args.category:raise ValueError('请指定官方category或已核验的request-file。')
                if args.request_file:
                    if args.category:raise ValueError('request-file不能与category混用。')
                    request=validate_request(json.loads(Path(args.request_file).read_text(encoding='utf-8')))
                    if request['startDate']!=args.date:raise ValueError('请求日期与date不符。')
            from .api_client import APIClient
            with APIClient({'platform':'jd','store_key':args.store},min_extension='0.9.16') as client:
                if args.category and args.command!='industry-options':
                    options,options_proof=client.request('industry-options',args.date);request_count+=1
                    request,query_scope=build_request(options,args.command.removeprefix('industry-'),args.date,
                        category=args.category,channel=args.channel,business=args.business,dimension=args.dimension)
                raw,proof=client.request(args.command,args.date,scope={'request':request} if request is not None else None)
                request_count+=1
            payload={'platform':'jd','store_key':args.store,'date':args.date,'command':args.command,'response':raw,'proof':proof,
                'query_scope':query_scope,'options_response':options,'options_proof':options_proof}
            folder=Path(__file__).resolve().parents[3]/'data/industry'/args.store.replace(':','_')/args.date/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex[:8])
            evidence=folder/'evidence.json';write_evidence(evidence,payload)
        verify_proof(proof,args.command,args.date,args.store)
        result=normalize(raw,args.command.removeprefix('industry-'),limit=args.limit)
        folder=Path(__file__).resolve().parents[3]/'data/industry'/args.store.replace(':','_')/args.date/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid4().hex[:8])
        report={'platform':'jd','store_key':args.store,'date':args.date,'command':args.command,
            'status':'partial','query_status':'ok','verification':'read_interface_verified; metrics retain official coverage and disclosure limits',
            'query_scope':query_scope,'collection_mode':'replay' if args.evidence else 'live','source_requests_this_call':request_count,
            'result':result,'evidence_path':str(evidence),'request':proof.get('request_body'),
            'limitations':['区间值、指数和缺失保持官方原值，不取中点、不强行解码或加总。','行业大盘与本店类目销售、同行均值分别解释。']}
        save_json(folder/'report.json',report)
        print(json.dumps({**report,'report_path':str(folder/'report.json')},ensure_ascii=False));return 0
    except (ValueError,KeyError,TypeError,OSError,RuntimeError) as exc:
        print(str(exc),file=sys.stderr);return 1
