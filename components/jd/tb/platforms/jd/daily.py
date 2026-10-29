"""JD daily workflow calculations; platform metric names remain unchanged."""
from datetime import date,timedelta
from statistics import median
import json
import sys
import time
import math
from .overview import numeric,formatted
from .data_scope import policy


def collect_overviews(day,store,count,*,transport='api'):
    from .cli import BridgeServer,JD,ROOT,capture,save_overview
    from . import reports,overview
    target=date.fromisoformat(day)
    template=reports.contracts()['overview']['template']
    if transport=='api':
        from .api_client import APIClient,capture_api
        rows=[];begin=time.perf_counter()
        with APIClient({'platform':'jd','store_key':store}) as client:
            for offset in range(count-1,-1,-1):
                selected=(target-timedelta(days=offset)).isoformat()
                request=overview.make_request(template,selected)
                result=capture_api('overview',selected,store,client=client)
                report,_=save_overview(result,request);rows.append(report)
        return rows,{'mode':'fresh_registered_api','days':count,'shared_bridge':True,'elapsed_ms':round((time.perf_counter()-begin)*1000)}
    bridge=BridgeServer(JD);started=False;rows=[];begin=time.perf_counter()
    try:
        bridge.start();started=True
        for offset in range(count-1,-1,-1):
            selected=(target-timedelta(days=offset)).isoformat()
            print('经营分析取数：'+selected,file=sys.stderr,flush=True)
            request=overview.make_request(template,selected)
            result=capture(request,'overview',{'platform':'jd','store_key':store},bridge=bridge)
            report,_=save_overview(result,request)
            rows.append(report)
    finally:
        if started:bridge.stop()
        else:bridge.server_close()
    return rows,{'mode':'fresh_native_responses','days':count,'shared_bridge':True,'elapsed_ms':round((time.perf_counter()-begin)*1000)}


def collect(day,store,*,transport='api'):
    from .cli import ROOT
    started=time.monotonic()
    rows,collection=collect_overviews(day,store,7,transport=transport)
    report=analyze(rows,day,store)
    from .refund_review import analyze as refund_analyze
    report['aftersales']=refund_analyze(rows,day,store)
    report['collection']=collection
    if transport=='api':
        from . import business_structure
        business_structure.attach(report,business_structure.collect(day,store,weekly=False))
        report['scope']='七日概况基线、两日官方有数据SPU、APP四层路径、两日六终端与已保存订单复盘；各域缺失与失败分开列示'
    collection['total_elapsed_ms']=round((time.monotonic()-started)*1000)
    folder=ROOT/'data/jd'/store.replace(':','_')/day/'daily-check'
    folder.mkdir(parents=True,exist_ok=True)
    report['report_path']=str(folder/'report.json')
    report['markdown_path']=str(folder/'report.md')
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (folder/'report.md').write_text(markdown(report),encoding='utf-8')
    return report


def validate_window(reports,day,store,count=7):
    target=date.fromisoformat(day)
    days=[(target-timedelta(days=offset)).isoformat() for offset in range(count-1,-1,-1)]
    label='七日' if count==7 else '十四日'
    if len(reports)!=count or sorted(row.get('date','') for row in reports)!=days:
        raise ValueError('必须提供连续'+label+'、无重复的同口径概况')
    ordered=sorted(reports,key=lambda row:row['date'])
    for row in ordered:
        if row.get('store',{}).get('platform')!='jd' or row['store'].get('store_key')!=store:
            raise ValueError(label+'报告店铺或平台不一致')
        if row.get('channel')!='全部':raise ValueError(label+'报告渠道必须均为全部')
        if row.get('compare_date')!=(date.fromisoformat(row['date'])-timedelta(days=1)).isoformat():
            raise ValueError(label+'报告对比日期不一致')
    tables=[{metric['field']:metric for metric in row['metrics']} for row in ordered]
    for index in range(1,count):
        for field,metric in tables[index].items():
            previous=numeric(metric.get('previous'))
            preceding=numeric(tables[index-1].get(field,{}).get('value'))
            unit=metric.get('unit')
            tolerance=0.01 if unit=='元' else 0 if unit in ('人','件','单','次') else 1e-8 if unit in ('%','fraction') else 1e-6
            if previous is not None and preceding is not None and not math.isclose(previous,preceding,rel_tol=0,abs_tol=tolerance):
                raise ValueError('相邻日期指标不一致：'+ordered[index]['date']+' '+field+'；请核对平台回补或统计口径')
    return ordered,tables,days


def analyze(reports,day,store):
    ordered,tables,days=validate_window(reports,day,store)
    current=ordered[-1]
    metrics=[]
    for metric in current['metrics']:
        values=[numeric(table.get(metric['field'],{}).get('value')) for table in tables]
        valid=[value for value in values if value is not None]
        baseline=median(valid) if len(valid)==7 else None
        value=numeric(metric.get('value'))
        metrics.append({**metric,'median7':baseline,'valid_days':len(valid),
          'vs_median7':value/baseline-1 if value is not None and baseline not in (None,0) else None,
          'median_source':'本次计算：D-6至D七个完整日中位数'})
    by_name={metric['name']:metric for metric in metrics}
    amount=by_name.get('成交金额',{})
    def comparable(metric):
        return numeric(metric.get('value')) is not None and numeric(metric.get('previous')) is not None
    amount_change=numeric(amount.get('relative_change')) if comparable(amount) else None
    direction='缺少可比数据' if amount_change is None else '上升' if amount_change>0 else '下降' if amount_change<0 else '持平'
    factors=[by_name[name] for name in ('店铺访客数','店铺成交转化率','客单价') if comparable(by_name.get(name,{})) and numeric(by_name.get(name,{}).get('relative_change')) is not None]
    aligned=[metric for metric in factors if amount_change is not None and metric['relative_change']*amount_change>0]
    aligned.sort(key=lambda metric:abs(metric['relative_change']),reverse=True)
    finding=f'成交金额较前一日{direction}。'
    if aligned:finding+='同向变化最大的已观测因子为'+aligned[0]['name']+'，仅描述伴随变化，不证明因果。'
    actions=[]
    if aligned:
        metric=aligned[0]
        actions.append({'action':'优先按商品和来源核查'+metric['name']+'变化集中位置，确认后再调整运营',
          'evidence':{'field':metric['field'],'value':metric['value'],'previous':metric['previous'],'relative_change':metric['relative_change']},
          'limitation':'商品接口截断和APP部分来源不能代表全店归因'})
    risks=[]
    refund=by_name.get('退款金额',{})
    if comparable(refund) and (numeric(refund.get('relative_change')) or 0)>0:
        risks.append({'name':'退款金额上升，需核查','field':refund['field'],'value':refund['value'],'previous':refund['previous'],
          'relative_change':refund['relative_change'],'median7':refund['median7'],
          'definition':'沿用京东页面退款金额口径；可能跨期，不能作为同期订单真实退货率或直接扣减为净销售'})
        actions.append({'action':'核对退款金额拆分及对应售后原因、原成交日期，确认增长集中环节',
          'evidence':{'field':refund['field'],'value':refund['value'],'previous':refund['previous'],'relative_change':refund['relative_change']},
          'limitation':'当前只有金额汇总；未取得原因和原订单队列'})
    return {'platform':'jd','store':current['store'],'module':'日体检','status':'partial',
      'scope':'交易概况七日基线；未替代原工作流的全部数据域',
      'date':day,'compare_date':current['compare_date'],'channel':'全部','baseline_dates':days,
      'metrics':metrics,'finding':finding,'actions':actions[:2],'risks':risks,
      'data_scope':policy(),
      'missing_sources':['京东同口径净成交/净支付定义','官方有数据商品与APP来源的当日证据及可比指标覆盖','官方售后与完整付款队列'],
      'sources':[{'date':row['date'],'request_timestamp':row.get('request_timestamp'),
        'source':row.get('source'),'response_sha256':row.get('response_sha256'),'report_path':row.get('report_path')} for row in ordered],
      'definitions':'成交金额保持京东原名；中位数包含目标日；缺失不补零。相邻日反向核对：金额容差0.01元，人数/件数/单数/次数为0，比例1e-8，其他1e-6。退款事件不能直接除以同期成交作为真实退货率。'}


def markdown(report):
    lines=['# 京东商智 · 日体检（已验证范围）','',
      f"日期：{report['date']}；对比：{report['compare_date']}；基线：{report['baseline_dates'][0]}—{report['date']}。",
      f"店铺：{(report['store'].get('name') or report['store']['store_key']).replace(chr(10),' ')}",'',report['finding'],'',
      '| 指标 | 当日 | 前一日 | 七日中位数 | 较中位数 |','|---|---:|---:|---:|---:|']
    for metric in report['metrics']:
        change='不可计算' if metric['vs_median7'] is None else f"{metric['vs_median7']*100:+.2f}%"
        lines.append('| '+metric['name']+' | '+' | '.join(formatted(metric.get(key),metric['unit']) for key in ('value','previous','median7'))+' | '+change+' |')
    lines+=['','## 需关注的信号',*['- '+risk['name']+'：'+formatted(risk['value'],'元')+'，前一日'+formatted(risk['previous'],'元')+'；'+risk['definition'] for risk in report['risks']],
      '','## 下一步动作',*['- '+action['action']+'。依据：'+action['evidence']['field']+'，当日'+str(action['evidence']['value'])+'、前一日'+str(action['evidence']['previous']) for action in report['actions']],
      '', '## 仍不能判断',*['- '+source for source in report['missing_sources']],
      '',report['definitions'],'','## 证据',*['- '+source['date']+'：'+(source['report_path'] or '未提供报告路径')+'；SHA256 '+(source['response_sha256'] or '未提供') for source in report['sources']],
      '','状态：partial；七日概况基线已计算不等于七个模块全部完成。','']
    from .business_structure import markdown as structure_markdown
    from .refund_review import markdown as refund_markdown
    return '\n'.join(lines)+structure_markdown(report.get('structure'))+(refund_markdown(report['aftersales']) if report.get('aftersales') else '')
