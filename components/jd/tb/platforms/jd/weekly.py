"""Rolling seven-day comparison from fourteen reconciled daily JD reports."""
import json,time
from .daily import collect_overviews,validate_window
from .overview import numeric,formatted
from .data_scope import policy


def analyze(reports,day,store):
    ordered,_,days=validate_window(reports,day,store,14)
    groups=[ordered[:7],ordered[7:]]
    def total(group,name):
        values=[numeric(next((metric.get('value') for metric in row['metrics'] if metric['name']==name),None)) for row in group]
        return sum(values) if all(value is not None for value in values) else None
    def ratio(a,b):return a/b if a is not None and b not in (None,0) else None
    metrics=[]
    def append(name,unit,values,definition):
        previous,value=values
        metrics.append({'name':name,'unit':unit,'value':value,'previous':previous,
          'relative_change':value/previous-1 if value is not None and previous not in (None,0) else None,'definition':definition})
    for name,unit in [('成交金额','元'),('成交商品件数','件'),('成交单量','单'),('退款金额','元')]:
        append(name,unit,[total(group,name) for group in groups],'本次计算：七个完整日官方同名指标加总；退款可能跨期，不据此推算退货率或净销售')
    append('成交客户人次','人次',[total(group,'成交客户数') for group in groups],'逐日成交客户数加总，跨日可能重复，不是周去重购买人数')
    append('日均店铺访客数','人',[ratio(total(group,'店铺访客数'),7) for group in groups],'每日店铺访客数的均值，不是周去重UV')
    append('按日汇总近似转化率','%',[ratio(total(group,'成交客户数'),total(group,'店铺访客数')) for group in groups],'本次计算：sum(日成交客户数)/sum(日店铺访客数)，按日汇总近似')
    append('按日汇总客单价','元',[ratio(total(group,'成交金额'),total(group,'成交客户数')) for group in groups],'本次计算：sum(日成交金额)/sum(日成交客户数)，使用逐日人次口径')
    by_name={metric['name']:metric for metric in metrics};amount=by_name['成交金额'];refund=by_name['退款金额']
    direction='无法比较' if amount['relative_change'] is None else '上升' if amount['relative_change']>0 else '下降' if amount['relative_change']<0 else '持平'
    actions=[]
    if amount['relative_change'] is not None and amount['relative_change']!=0:
        actions.append({'action':'按两周相同范围补齐商品和来源结构，确认成交变化集中位置',
          'evidence':{'metric':'成交金额','value':amount['value'],'previous':amount['previous']},'limitation':'当前概况不能解释商品或渠道归因'})
    if refund['relative_change'] is not None and refund['relative_change']>0:
        actions.append({'action':'核对退款拆分、原因及原成交日期，区分新增成交与跨期售后',
          'evidence':{'metric':'退款金额','value':refund['value'],'previous':refund['previous']},'limitation':'不将退款事件直接除以当周成交作为退货率'})
    return {'platform':'jd','store':ordered[-1]['store'],'module':'周复盘','status':'partial','date':day,'channel':'全部',
      'current_period':[days[7],days[-1]],'previous_period':[days[0],days[6]],
      'finding':'近七个完整日成交金额较前七日'+direction+'；仅反映概况结果，结构原因仍需验证。',
      'metrics':metrics,'deduplicated_week_uv':None,'actions':actions[:2],
      'data_scope':policy(),
      'missing_sources':['原生区间去重UV/成交客户数','官方有数据商品与APP来源的同窗证据及可比指标覆盖','商品评价、完整售后与原付款队列','同口径净成交定义'],
      'sources':[{'date':row['date'],'request_timestamp':row.get('request_timestamp'),'response_sha256':row.get('response_sha256'),'report_path':row.get('report_path')} for row in ordered]}


def markdown(report):
    lines=['# 京东商智 · 周复盘（已验证范围）','',
      f"近七日：{'—'.join(report['current_period'])}；前七日：{'—'.join(report['previous_period'])}。",'',report['finding'],'',
      '| 指标 | 近七日 | 前七日 | 变化 |','|---|---:|---:|---:|']
    for metric in report['metrics']:
        change='不可计算' if metric['relative_change'] is None else f"{metric['relative_change']*100:+.2f}%"
        lines.append('| '+metric['name']+' | '+formatted(metric['value'],metric['unit'])+' | '+formatted(metric['previous'],metric['unit'])+' | '+change+' |')
    lines+=['','## 计算口径',*['- '+metric['name']+'：'+metric['definition'] for metric in report['metrics']],
      '','## 下一步动作',*['- '+item['action']+'。依据：'+str(item['evidence']) for item in report['actions']],
      '','## 不能判断',*['- '+item for item in report['missing_sources']],
      '','状态：partial；不是完整七模块验收。','']
    from .business_structure import markdown as structure_markdown
    from .refund_review import markdown as refund_markdown
    return '\n'.join(lines)+structure_markdown(report.get('structure'))+(refund_markdown(report['aftersales']) if report.get('aftersales') else '')


def collect(day,store,*,transport='api'):
    from .cli import ROOT
    started=time.monotonic()
    rows,collection=collect_overviews(day,store,14,transport=transport)
    report=analyze(rows,day,store);report['collection']=collection
    from .refund_review import analyze as refund_analyze
    report['aftersales']=refund_analyze(rows,day,store,weekly=True)
    if transport=='api':
        from . import business_structure
        business_structure.attach(report,business_structure.collect(day,store,weekly=True,overview_reports=rows))
        if report['structure']['products'].get('status')=='ok':
            report['missing_sources']=['原生区间去重UV/成交客户数','APP来源树同窗证据及可比指标覆盖','商品评价、完整售后与原付款队列','同口径净成交定义']
    collection['total_elapsed_ms']=round((time.monotonic()-started)*1000)
    folder=ROOT/'data/jd'/store.replace(':','_')/day/'weekly-review';folder.mkdir(parents=True,exist_ok=True)
    report.update(report_path=str(folder/'report.json'),markdown_path=str(folder/'report.md'))
    (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (folder/'report.md').write_text(markdown(report),encoding='utf-8')
    return report
