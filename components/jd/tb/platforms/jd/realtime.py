"""Today-only trade snapshot; kept separate from complete-day reporting."""
from datetime import datetime,timedelta,timezone
import json
from .api_client import ROOT,APIClient
from .overview import summarize as summarize_daily,formatted

CHINA=timezone(timedelta(hours=8))
def now_china():return datetime.now(CHINA)
def contract():return json.loads((ROOT/'extension/unpacked/realtime-contract.json').read_text(encoding='utf-8'))

def make_body(*,now=None):
    current=(now or now_china()).astimezone(CHINA).replace(microsecond=0)
    day=current.date().isoformat();prior=(current.date()-timedelta(days=1)).isoformat();clock=current.strftime('%H:%M:%S')
    return {**contract()['template'],'startDate':day+' 00:00:00','endDate':day+' '+clock,
      'compareStartDate':prior+' 00:00:00','compareEndDate':prior+' '+clock}

def summarize(payload,request,proof):
    if request.get('realtime') is not True or request.get('dateType')!='todayRealtime' or request.get('interval')!='SECOND':raise ValueError('不是已登记实时合同')
    report=summarize_daily(payload,request,'registered-api',proof.get('request_started_at'))
    allowed=set(contract()['template']['indicators'])
    report['metrics']=[{**m,'previous':None,'relative_change':None,'change_pp':None,'change_source':'未请求对照指标'} for m in report['metrics'] if m['field'] in allowed]
    if not any(m['value'] is not None for m in report['metrics']):raise ValueError('实时核心指标全部缺失')
    report.update(date=request['startDate'][:10],realtime=True,is_complete_day=False,channel='全部',compare_date=None,compare_type='未核验对照，不计算增长',
      requested_from=request['startDate'],requested_until=request['endDate'],timezone='Asia/Shanghai',data_as_of=None,
      received_at=proof.get('received_at'),query_proof=proof,
      missing_metrics=[m['name'] for m in report['metrics'] if m['value'] is None],
      definitions='官方实时交易概况；查询截至时间不等于平台数据更新时间，接口未核实数据更新时间。成交金额不是支付金额或净销售。未请求对照指标，不与昨日全天比较。缺失值不补零。')
    return report

def collect(store):
    with APIClient({'platform':'jd','store_key':store},min_extension='0.9.1') as client:
        day=now_china().date().isoformat();payload,proof=client.request('overview-realtime',day)
        if datetime.fromisoformat(proof['request_started_at'].replace('Z','+00:00')).astimezone(CHINA).date().isoformat()!=day:raise ValueError('请求跨日，请重新查询实时数据')
        request=proof['request_body'];report=summarize(payload,request,proof)
        report.update(platform='jd',store=proof['identity'],shop=proof['identity'].get('name'),status='ok' if not report['missing_metrics'] else 'partial')
        stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        folder=ROOT/'data/jd'/store.replace(':','_')/day/'shop-realtime'/stamp;folder.mkdir(parents=True,exist_ok=True)
        (folder/'response.json').write_text(client.last_response_text,encoding='utf-8')
        report.update(report_path=str(folder/'report.json'),markdown_path=str(folder/'report.md'))
        (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        lines=['# 京东商智 · 实时交易概况','',f"查询范围：{request['startDate']} 至 {request['endDate']}（北京时间）。",'平台数据更新时间：接口未核实。','', '| 指标 | 当前值 |','|---|---:|']
        lines += ['| '+m['name']+' | '+formatted(m['value'],m['unit'])+' |' for m in report['metrics']]
        lines += ['',report['definitions'],'',f"请求时间：{proof['request_started_at']}；响应正文 SHA256：{proof['response_sha256']}。"]
        (folder/'report.md').write_text('\n'.join(lines),encoding='utf-8')
        return report
