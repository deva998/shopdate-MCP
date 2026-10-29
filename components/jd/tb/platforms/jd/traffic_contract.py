"""Observed APP traffic-source contract; names require matching live-page evidence."""
from datetime import date,timedelta
from copy import deepcopy
from .overview import numeric

ENDPOINT='https://szgateway.jd.com/api/lowcode/flowSource/sourceTable/table.ajax'
GROUP1='jdr_sch_traffic_cha_last_field_src_rmad_sz_1'
GROUP2='jdr_sch_traffic_cha_last_field_src_rmad_sz_2'
UV='jdr_sch_traffic_brow_sku_cnt_jd_unified_attribution_sz'
AMOUNT='jdr_sch_traffic_intr_ord_ord_amt_jd_unified_attribution_trade_deal_snapshot_sz'
FIELDS=[('引入商详访客数',UV,'人'),('引入成交金额',AMOUNT,'元'),
 ('引入浏览量','jdr_sch_traffic_brow_sku_qtty_jd_unified_attribution_sz','次'),
 ('引入成交客户数','jdr_sch_traffic_intr_ord_ord_cnt_jd_unified_attribution_trade_deal_snapshot_sz','人'),
 ('引入成交转化率','fo_jdr_sch_fo_jdr_sch_traffic_intr_ord_cvr_deal_sz','fraction'),
 ('UV价值','fo_jdr_sch_traffic_uv_value_jd_unified_attribution_sz','元')]


def name_sources(report,payload):
    """Join only the requested tree level, never guess names across parents."""
    if payload.get('header',{}).get('code')!=0 or payload.get('errors'):raise ValueError('来源字典业务状态失败')
    nodes=payload.get('body',{}).get('data')
    def index(rows):
        if not isinstance(rows,list) or len(rows)>10000:raise ValueError('来源字典结构无效')
        result={}
        for node in rows:
            if not isinstance(node,dict) or not isinstance(node.get('value'),str) or not isinstance(node.get('name'),str) or not node['name'].strip():raise ValueError('来源字典缺少编号或名称')
            if node['value'] in result:raise ValueError('同层级来源字典编号重复')
            result[node['value']]=node
        return result
    roots=index(nodes)
    if report.get('group')==GROUP1:lookup=roots
    elif report.get('group')==GROUP2 and report.get('parent_ids')==['2']:
        lookup=index(roots.get('2',{}).get('child'))
    else:raise ValueError('来源层级或父级未验证')
    output=deepcopy(report);missing=[]
    for row in output['rows']:
        row['name']=lookup.get(row['source_id'],{}).get('name')
        if row['name'] is None:missing.append(row['source_id'])
    output['source_names']={'mapped_sources':len(output['rows'])-len(missing),'unmapped_ids':missing,'method':'exact_id_and_parent_dictionary'}
    output['notes']=[n for n in output.get('notes',[]) if not n.startswith('来源名称字典待验证')]
    output['notes'].append('来源名称按官方字典编号及父级匹配；未知来源保留空值；字典读取时间不等于历史指标日期')
    return output

def parse_sample(sample, *, sample_only=True):
    if sample.get('url')!=ENDPOINT or sample.get('method')!='POST' or sample.get('status')!=200:
        raise ValueError('不是成功的流量来源表响应')
    request=sample.get('request_body') or {}
    selected=date.fromisoformat(request.get('startDate',''))
    day=selected.isoformat();previous=(selected-timedelta(days=1)).isoformat()
    expected={'realtime':False,'interval':'DAY','dateType':'day','startDate':day,'endDate':day,
      'compareStartDate':previous,'compareEndDate':previous,'compareType':'hb','channel':'app','spuIds':[]}
    if any(type(request.get(key)) is not type(value) or request.get(key)!=value for key,value in expected.items()):
        raise ValueError('只验证APP、单日、前一日对比、无单品筛选合同')
    groups=request.get('groups')
    if groups not in ([GROUP1],[GROUP2]) or request.get('attributes')!=groups:
        raise ValueError('流量来源层级未验证')
    if groups==[GROUP2] and request.get('flowSrcId1')!=['2']:
        raise ValueError('尚未验证其他父级来源')
    response=sample.get('response') or {}
    if response.get('header',{}).get('code')!=0 or response.get('errors'):
        raise ValueError('流量接口业务状态失败')
    body=response.get('body') or {};data=body.get('data')
    if not isinstance(data,list):raise ValueError('缺少流量来源数据数组')
    seen=set();rows=[]
    for row in data:
        key=row.get(groups[0]) if isinstance(row,dict) else None
        if not isinstance(key,str) or not key or key in seen:raise ValueError('来源编号缺失或重复')
        seen.add(key)
        rows.append({'source_id':key,'name':None,'metrics':{
          name:{'field':field,'unit':unit,'value':numeric(row.get(field)),
           'previous':numeric(row.get(field+'##compareValue')),'relative_change':numeric(row.get(field+'##compare'))}
           for name,field,unit in FIELDS}})
    size=body.get('size')
    incomplete=isinstance(size,int) and not isinstance(size,bool) and size>len(data)
    return {'date':day,'compare_date':previous,'channel':'app','group':groups[0],
      'parent_ids':request.get('flowSrcId1',[]),'page_index':request.get('pageIndex'),
      'page_size':request.get('pageSize'),'reported_size':size,'captured_rows':len(rows),'rows':rows,
      'coverage':'sample_only' if sample_only else 'requested_level_page','complete':False if incomplete else None,
      'complete_for_request':not incomplete if not sample_only and isinstance(size,int) else None,
      'notes':['来源名称字典待验证，保留编号，不按数字猜测渠道名称',
       '各层级分开保留，不将父级与子级相加；来源UV不可直接相加作为全店去重UV',
       '当前只验证APP，不可当作全部渠道；样本截取不代表完整来源列表']}
